import tkinter as tk
from tkinter import font as tkFont
from datetime import date

WINDOW_WIDTH = 360
WINDOW_HEIGHT = 520
CARD_RADIUS = 24
TRANSPARENT_KEY = "#010203"

TEXT_PRIMARY = "#111111"
TEXT_SOFT = "#2A2A2A"
WHITE = "#FFFFFF"

THEMES = [
    {"front": "#E94B91", "back": "#CF3A7A", "ink": "#2A1222", "accent": "#FFD7EA"},
    {"front": "#F26A2E", "back": "#DB5720", "ink": "#2A150C", "accent": "#FFE2CF"},
    {"front": "#2F6FED", "back": "#245BD0", "ink": "#101A33", "accent": "#DCE8FF"},
    {"front": "#15A86B", "back": "#108A58", "ink": "#0F2A1F", "accent": "#D3F8E8"},
]

def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(max(0, min(255, rgb[0])), max(0, min(255, rgb[1])), max(0, min(255, rgb[2])))


def _blend(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex((
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    ))


def _rounded_points(x1, y1, x2, y2, radius):
    return [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]


class PillButton:
    def __init__(self, parent, text, color, command, width=94, height=32):
        self.command = command
        self.base = _blend(color, "#101114", 0.78)
        self.border = color
        self.label_color = color
        self.hover = _blend(self.base, WHITE, 0.10)
        self.press = _blend(self.base, "#000000", 0.20)
        self.width = width
        self.height = height

        self.canvas = tk.Canvas(parent, width=width, height=height, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self.shape = self.canvas.create_polygon(
            _rounded_points(1, 1, width - 1, height - 1, 14),
            smooth=True,
            splinesteps=20,
            fill=self.base,
            outline=self.border,
            width=1,
        )
        self.label = self.canvas.create_text(
            width / 2,
            height / 2,
            text=text,
            font=("Cascadia Code", 9, "bold"),
            fill=self.label_color,
        )

        for item in (self.shape, self.label):
            self.canvas.tag_bind(item, "<Enter>", self._on_enter)
            self.canvas.tag_bind(item, "<Leave>", self._on_leave)
            self.canvas.tag_bind(item, "<ButtonPress-1>", self._on_press)
            self.canvas.tag_bind(item, "<ButtonRelease-1>", self._on_release)

    def _on_enter(self, _event):
        self.canvas.itemconfig(self.shape, fill=self.hover)

    def _on_leave(self, _event):
        self.canvas.itemconfig(self.shape, fill=self.base)

    def _on_press(self, _event):
        self.canvas.itemconfig(self.shape, fill=self.press)

    def _on_release(self, event):
        self.canvas.itemconfig(self.shape, fill=self.hover)
        if 0 <= event.x <= self.width and 0 <= event.y <= self.height:
            self.command()

    def pack(self, **kwargs):
        self.canvas.pack(**kwargs)


class FlashcardUI:
    _app_root = None
    _close_all_requested = False

    @classmethod
    def _get_app_root(cls):
        if cls._app_root is None:
            cls._app_root = tk.Tk()
            cls._app_root.withdraw()
        return cls._app_root

    def __init__(self, flashcard_qa: dict):
        self.flashcard_qa = flashcard_qa
        self.user_choice = None
        self.is_front = True
        self.is_animating = False
        self._type_job = None

        theme_index = abs(hash(self.flashcard_qa.get("Q", ""))) % len(THEMES)
        self.theme = THEMES[theme_index]

        app_root = self._get_app_root()
        self.root = tk.Toplevel(app_root)
        self.root.title("Flashcard")
        self.root.overrideredirect(True)
        self.root.configure(bg=TRANSPARENT_KEY)
        self.root.wm_attributes("-topmost", 1)

        try:
            self.root.wm_attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass

        x = self.root.winfo_screenwidth() - (WINDOW_WIDTH + 40)
        y = 40
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

        self.root.bind("<Escape>", lambda _e: self._close_window())
        self.root.bind("<ButtonPress-1>", self._start_move)
        self.root.bind("<ButtonRelease-1>", self._stop_move)
        self.root.bind("<B1-Motion>", self._do_move)
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)

        self.title_font = tkFont.Font(family="Cascadia Code", size=11, weight="bold")
        self.date_font = tkFont.Font(family="Cascadia Code", size=11, weight="bold")
        self.q_font = tkFont.Font(family="Cascadia Code", size=18, weight="bold")
        self.a_font = tkFont.Font(family="Cascadia Code", size=15, weight="bold")
        self.meta_font = tkFont.Font(family="Cascadia Code", size=9, weight="bold")

        self.canvas = tk.Canvas(self.root, width=WINDOW_WIDTH, height=WINDOW_HEIGHT, bg=TRANSPARENT_KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.card_center_x = WINDOW_WIDTH // 2
        self.card_center_y = WINDOW_HEIGHT // 2

        self._draw_card_frame()
        self._create_card_content()
        self._create_back_buttons()

    def _start_move(self, event):
        self.root._drag_x = event.x
        self.root._drag_y = event.y

    def _stop_move(self, _event):
        self.root._drag_x = None
        self.root._drag_y = None

    def _do_move(self, event):
        if getattr(self.root, "_drag_x", None) is None:
            return
        nx = self.root.winfo_x() + (event.x - self.root._drag_x)
        ny = self.root.winfo_y() + (event.y - self.root._drag_y)
        self.root.geometry(f"+{nx}+{ny}")

    def _draw_card_frame(self):
        # Card shadow
        self.canvas.create_polygon(
            _rounded_points(8, 10, WINDOW_WIDTH - 6, WINDOW_HEIGHT - 2, CARD_RADIUS),
            smooth=True,
            splinesteps=24,
            fill=_blend("#000000", self.theme["back"], 0.72),
            outline="",
        )

        # Main rounded card filling almost entire window.
        self.card_shape = self.canvas.create_polygon(
            _rounded_points(2, 2, WINDOW_WIDTH - 2, WINDOW_HEIGHT - 10, CARD_RADIUS),
            smooth=True,
            splinesteps=28,
            fill=self.theme["front"],
            outline=_blend(self.theme["front"], WHITE, 0.2),
            width=1,
        )

        self.card_gloss = self.canvas.create_polygon(
            _rounded_points(16, 26, WINDOW_WIDTH - 16, 122, 16),
            smooth=True,
            splinesteps=24,
            fill=_blend(WHITE, self.theme["front"], 0.72),
            outline="",
            width=0,
        )

        # Transition veil used for blur/reveal animation.
        self.transition_veil = self.canvas.create_polygon(
            _rounded_points(2, 2, WINDOW_WIDTH - 2, WINDOW_HEIGHT - 10, CARD_RADIUS),
            smooth=True,
            splinesteps=24,
            fill=_blend(self.theme["front"], WHITE, 0.18),
            outline="",
            state="hidden",
        )

        self.top_left_title = self.canvas.create_text(
            34,
            58,
            text="DAILY",
            anchor="w",
            fill=TEXT_PRIMARY,
            font=("Cascadia Code", 20, "bold"),
        )
        self.top_left_subtitle = self.canvas.create_text(
            34,
            84,
            text="REMINDER",
            anchor="w",
            fill=TEXT_PRIMARY,
            font=("Cascadia Code", 11, "bold"),
        )

        self.close_btn = self.canvas.create_text(
            WINDOW_WIDTH - 16,
            16,
            text="x",
            anchor="center",
            fill=TEXT_PRIMARY,
            font=("Cascadia Code", 10, "bold"),
        )
        self.canvas.tag_bind(self.close_btn, "<Button-1>", lambda _e: self._request_close_all())

    def _request_close_all(self):
        FlashcardUI._close_all_requested = True
        self._close_window()

    def _create_card_content(self):
        day_num = date.today().day
        month_txt = date.today().strftime("%b").upper()

        self.day_text = self.canvas.create_text(
            WINDOW_WIDTH - 56,
            62,
            text=f"{day_num}",
            fill=TEXT_PRIMARY,
            font=("Cascadia Code", 32, "bold"),
        )
        self.month_text = self.canvas.create_text(
            WINDOW_WIDTH - 56,
            90,
            text=f"{month_txt}",
            fill=TEXT_PRIMARY,
            font=("Cascadia Code", 10, "bold"),
        )

        self.title_text = self.canvas.create_text(
            34,
            128,
            text="",
            anchor="w",
            fill=TEXT_PRIMARY,
            font=self.title_font,
        )

        self.body_text = self.canvas.create_text(
            34,
            224,
            text=self.flashcard_qa.get("Q", "N/A"),
            anchor="w",
            width=WINDOW_WIDTH - 68,
            justify="left",
            fill=TEXT_PRIMARY,
            font=self.q_font,
        )

        self.footer_text = self.canvas.create_text(
            34,
            WINDOW_HEIGHT - 100,
            text="TAP CARD TO FLIP",
            anchor="w",
            fill=TEXT_PRIMARY,
            font=self.meta_font,
        )

        for item in [
            self.card_shape,
            self.card_gloss,
            self.title_text,
            self.body_text,
            self.footer_text,
            self.day_text,
            self.month_text,
            self.top_left_title,
            self.top_left_subtitle,
        ]:
            self.canvas.tag_bind(item, "<Button-1>", lambda _e: self.flip_card())

    def _create_back_buttons(self):
        self.button_row = tk.Frame(self.root, bg=self.theme["front"])
        self.button_row.place(x=20, y=WINDOW_HEIGHT - 86, width=WINDOW_WIDTH - 40, height=48)

        # Semantic hues + card accent blend: readable meaning and visual harmony.
        easy_color = _blend("#39E58C", self.theme["accent"], 0.35)
        medium_color = _blend("#FFC95E", self.theme["accent"], 0.35)
        hard_color = _blend("#FF6C96", self.theme["accent"], 0.35)

        self.btn_easy = PillButton(self.button_row, "EASY", easy_color, lambda: self._choose("EASY"))
        self.btn_medium = PillButton(self.button_row, "MEDIUM", medium_color, lambda: self._choose("MEDIUM"))
        self.btn_hard = PillButton(self.button_row, "HARD", hard_color, lambda: self._choose("HARD"))

    def _set_face_content(self, front: bool, width: int):
        fill = self.theme["front"] if front else self.theme["back"]
        ink = TEXT_PRIMARY
        soft = TEXT_SOFT

        self.canvas.itemconfig(self.card_shape, fill=fill, outline=_blend(fill, WHITE, 0.2))
        self.canvas.itemconfig(self.card_gloss, fill=_blend(WHITE, fill, 0.72))
        self.button_row.config(bg=fill)

        self.canvas.itemconfig(self.day_text, fill=ink)
        self.canvas.itemconfig(self.month_text, fill=soft)

        if front:
            self.canvas.itemconfig(self.title_text, text="")
            self.canvas.itemconfig(self.body_text, text=self.flashcard_qa.get("Q", "N/A"), font=self.q_font)
            self.canvas.itemconfig(self.footer_text, text="TAP CARD TO FLIP")
        else:
            self.canvas.itemconfig(self.title_text, text="")
            self.canvas.itemconfig(self.body_text, text=self.flashcard_qa.get("A", "N/A"), font=self.a_font)
            # Footer text is hidden on back face to avoid overlap artifacts near the buttons.
            self.canvas.itemconfig(self.footer_text, text="")

        self.canvas.itemconfig(self.title_text, fill=soft)
        self.canvas.itemconfig(self.body_text, fill=ink, width=WINDOW_WIDTH - 68)
        self.canvas.itemconfig(self.footer_text, fill=soft)

    def _animate_answer_typing(self, full_text: str, i: int = 0):
        if i > len(full_text):
            self._type_job = None
            return
        self.canvas.itemconfig(self.body_text, text=full_text[:i])
        self._type_job = self.root.after(9, lambda: self._animate_answer_typing(full_text, i + 1))

    def _run_blur_transition(self, to_front: bool):
        cover_steps = 8
        reveal_steps = 8
        from_fill = self.theme["front"] if self.is_front else self.theme["back"]
        to_fill = self.theme["front"] if to_front else self.theme["back"]

        self.canvas.itemconfig(self.transition_veil, state="normal")

        def cover(i=0):
            if i > cover_steps:
                self.is_front = to_front
                self._set_face_content(self.is_front, WINDOW_WIDTH)

                # Type-in reveal for the answer side for a smoother transition.
                if not self.is_front:
                    if self._type_job is not None:
                        self.root.after_cancel(self._type_job)
                        self._type_job = None
                    answer_text = self.flashcard_qa.get("A", "N/A")
                    self.canvas.itemconfig(self.body_text, text="")
                    self._animate_answer_typing(answer_text, 0)

                reveal(0)
                return

            t = i / cover_steps
            veil_color = _blend(from_fill, WHITE, 0.10 + (0.30 * t))
            self.canvas.itemconfig(self.transition_veil, fill=veil_color)
            # Slightly fade text under veil to mimic blur.
            self.canvas.itemconfig(self.body_text, fill=TEXT_SOFT)
            self.root.after(18, lambda: cover(i + 1))

        def reveal(i=0):
            if i > reveal_steps:
                self.canvas.itemconfig(self.transition_veil, state="hidden")
                self._toggle_buttons()
                self.is_animating = False
                return

            t = i / reveal_steps
            veil_color = _blend(to_fill, WHITE, 0.40 - (0.35 * t))
            self.canvas.itemconfig(self.transition_veil, fill=veil_color)
            self.root.after(18, lambda: reveal(i + 1))

        cover(0)

    def flip_card(self):
        if self.is_animating:
            return
        self.is_animating = True
        self._run_blur_transition(to_front=not self.is_front)

    def _toggle_buttons(self):
        for widget in self.button_row.winfo_children():
            widget.pack_forget()
        if self.is_front:
            return
        self.btn_easy.pack(side="left", padx=4)
        self.btn_medium.pack(side="left", padx=4)
        self.btn_hard.pack(side="left", padx=4)

    def _choose(self, choice):
        self.user_choice = choice
        self._close_window()

    def _close_window(self):
        if self._type_job is not None:
            try:
                self.root.after_cancel(self._type_job)
            except Exception:
                pass
            self._type_job = None
        if self.root.winfo_exists():
            self.root.destroy()

    def run(self):
        self.root.grab_set()
        self.root.wait_window()
        return self.user_choice


if __name__ == "__main__":
    sample_card = {
        "Q": "How to build your first employee onboarding experience?",
        "A": "Start with a week-1 checklist, clear tool access, a peer buddy, and defined goals so the new hire gets confidence quickly.",
        "difficulty": "MEDIUM",
        "interval": 5,
        "last_reviewed": date(2026, 3, 20),
        "next_review": date(2026, 3, 25),
    }

    ui = FlashcardUI(sample_card)
    choice = ui.run()
    print(f"User chose: {choice}")
