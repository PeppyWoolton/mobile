# -*- coding: utf-8 -*-
"""Мобильное приложение (Android, Kivy) — «Вязальное производство».

Версия 1: чтение из десктопной базы через mobile_server.py:
  • Аналитика периода (план/факт/выполнение, машины, отставания);
  • Загрузка машин (по РЦ, % загрузки).

Сетевые запросы идут в фоновом потоке; UI обновляется в главном через Clock.
Адрес сервера и ключ сохраняются в settings.json (user_data_dir).
"""
import os
import json
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.progressbar import ProgressBar

from api import Api, ApiError

BG = (0.07, 0.08, 0.10, 1)
CARD = (0.13, 0.15, 0.18, 1)
ACCENT = (0.20, 0.55, 0.90, 1)
TXT = (0.92, 0.94, 0.96, 1)
MUT = (0.62, 0.66, 0.72, 1)


def _row(label, value, big=False):
    b = BoxLayout(size_hint_y=None, height=dp(38 if not big else 56), padding=(dp(12), 0))
    b.add_widget(Label(text=label, color=MUT, halign="left", valign="middle",
                       font_size=dp(15), text_size=(dp(180), None)))
    b.add_widget(Label(text=str(value), color=TXT, halign="right", valign="middle",
                       font_size=dp(24 if big else 16), bold=big,
                       text_size=(dp(150), None)))
    return b


class KnitApp(App):
    def build(self):
        self.title = "Вязальное производство"
        self.api = Api()
        self.period = None
        self.periods = []
        self._load_settings()

        root = BoxLayout(orientation="vertical")
        with_bg(root, BG)

        # ── панель подключения ────────────────────────────────────────────
        conn = GridLayout(cols=1, size_hint_y=None, height=dp(150),
                          padding=dp(8), spacing=dp(6))
        with_bg(conn, CARD)
        self.url_in = TextInput(text=self.api.base_url, hint_text="http://IP:8765",
                                multiline=False, size_hint_y=None, height=dp(40),
                                write_tab=False)
        self.key_in = TextInput(text=self.api.key, hint_text="ключ (если задан)",
                                multiline=False, password=True, size_hint_y=None,
                                height=dp(40), write_tab=False)
        line = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.connect_btn = Button(text="Подключить", background_color=ACCENT,
                                  on_release=lambda *_: self.connect())
        self.period_sp = Spinner(text="период", values=[],
                                 on_text=lambda *_: self.on_period())
        line.add_widget(self.connect_btn)
        line.add_widget(self.period_sp)
        conn.add_widget(self.url_in)
        conn.add_widget(self.key_in)
        conn.add_widget(line)
        root.add_widget(conn)

        # ── переключатель экранов ─────────────────────────────────────────
        tabs = BoxLayout(size_hint_y=None, height=dp(46))
        self.tab_an = Button(text="Аналитика", on_release=lambda *_: self.show("an"))
        self.tab_ml = Button(text="Машины", on_release=lambda *_: self.show("ml"))
        tabs.add_widget(self.tab_an)
        tabs.add_widget(self.tab_ml)
        root.add_widget(tabs)

        # ── контент со скроллом ───────────────────────────────────────────
        self.status = Label(text="Введите адрес сервера и нажмите «Подключить».",
                            color=MUT, size_hint_y=None, height=dp(30), font_size=dp(14))
        root.add_widget(self.status)

        self.scroll = ScrollView()
        self.content = GridLayout(cols=1, size_hint_y=None, spacing=dp(6),
                                  padding=(0, dp(4)))
        self.content.bind(minimum_height=self.content.setter("height"))
        self.scroll.add_widget(self.content)
        root.add_widget(self.scroll)

        self.view = "an"
        if self.api.base_url:
            Clock.schedule_once(lambda *_: self.connect(), 0.3)
        return root

    # ── настройки ─────────────────────────────────────────────────────────
    def _settings_path(self):
        return os.path.join(self.user_data_dir, "settings.json")

    def _load_settings(self):
        try:
            with open(self._settings_path(), encoding="utf-8") as f:
                s = json.load(f)
            self.api = Api(s.get("url", ""), s.get("key", ""))
        except Exception:
            self.api = Api()

    def _save_settings(self):
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump({"url": self.api.base_url, "key": self.api.key}, f)
        except Exception:
            pass

    # ── действия ──────────────────────────────────────────────────────────
    def connect(self):
        self.api = Api(self.url_in.text.strip(), self.key_in.text.strip())
        self._save_settings()
        self._set_status("Подключение…")
        self._bg(self.api.periods, self._on_periods)

    def _on_periods(self, periods, err):
        if err:
            return self._set_status(f"Ошибка: {err}")
        self.periods = periods or []
        names = [p["name"] for p in self.periods]
        self.period_sp.values = names
        active = next((p["name"] for p in self.periods if p.get("is_active")), None)
        self.period = active or (names[0] if names else None)
        if self.period:
            self.period_sp.text = self.period
            self.refresh()
        else:
            self._set_status("Периоды не найдены.")

    def on_period(self):
        if self.period_sp.text and self.period_sp.text != self.period:
            self.period = self.period_sp.text
            self.refresh()

    def show(self, view):
        self.view = view
        self.tab_an.background_color = ACCENT if view == "an" else (0.2, 0.22, 0.25, 1)
        self.tab_ml.background_color = ACCENT if view == "ml" else (0.2, 0.22, 0.25, 1)
        self.refresh()

    def refresh(self):
        if not self.period:
            return
        self._set_status("Загрузка…")
        if self.view == "an":
            self._bg(lambda: self.api.analytics(self.period), self._render_analytics)
        else:
            self._bg(lambda: self.api.machine_load(self.period), self._render_machines)

    # ── рендер ──────────────────────────────────────────────────────────────
    def _render_analytics(self, a, err):
        self.content.clear_widgets()
        if err:
            return self._set_status(f"Ошибка: {err}")
        self._set_status(f"Период: {a['период']}")
        self.content.add_widget(_row("Выполнение", f"{a['выполнение_%']} %", big=True))
        for lbl, key in [("План, пар", "план_пар"), ("Факт, пар", "факт_пар"),
                         ("Остаток, пар", "остаток_пар"), ("Заданий", "заданий"),
                         ("Не назначено", "не_назначено"),
                         ("Машин активно", "машин_активно"),
                         ("Машин задействовано", "машин_задействовано"),
                         ("Средняя загрузка, пар", "средняя_загрузка_пар")]:
            self.content.add_widget(_row(lbl, a.get(key, "—")))
        lag = a.get("топ_отставаний") or []
        if lag:
            self.content.add_widget(_header("Топ отставаний"))
            for r in lag:
                txt = f"{r['art']} {r.get('color','')}".strip()
                self.content.add_widget(_row(txt, f"−{r['остаток']}"))

    def _render_machines(self, rows, err):
        self.content.clear_widgets()
        if err:
            return self._set_status(f"Ошибка: {err}")
        self._set_status(f"Машин: {len(rows)}")
        cur = None
        for r in rows:
            if r["rc"] != cur:
                cur = r["rc"]
                self.content.add_widget(_header(f"РЦ {cur} игл"))
            card = BoxLayout(orientation="vertical", size_hint_y=None,
                             height=dp(62), padding=(dp(12), dp(6)), spacing=dp(4))
            with_bg(card, CARD)
            top = BoxLayout(size_hint_y=None, height=dp(24))
            st = "" if str(r.get("status", "")).startswith("Актив") else f"  ({r.get('status','')})"
            top.add_widget(Label(text=f"№{r['machine']}{st}", color=TXT,
                                 halign="left", valign="middle", font_size=dp(16),
                                 text_size=(dp(180), None)))
            top.add_widget(Label(text=f"{r['plan_пар']} пар · {r['sku']} SKU · {r['загрузка_%']}%",
                                 color=MUT, halign="right", valign="middle",
                                 font_size=dp(13), text_size=(dp(180), None)))
            card.add_widget(top)
            pb = ProgressBar(max=100, value=r["загрузка_%"], size_hint_y=None, height=dp(10))
            card.add_widget(pb)
            self.content.add_widget(card)

    # ── фон/утилиты ─────────────────────────────────────────────────────────
    def _bg(self, fn, done):
        def work():
            try:
                res, err = fn(), None
            except ApiError as e:
                res, err = None, str(e)
            except Exception as e:
                res, err = None, str(e)
            Clock.schedule_once(lambda *_: done(res, err), 0)
        threading.Thread(target=work, daemon=True).start()

    def _set_status(self, t):
        self.status.text = t


def _header(text):
    lb = Label(text=text, color=ACCENT, bold=True, size_hint_y=None, height=dp(34),
               halign="left", valign="middle", font_size=dp(15))
    lb.bind(size=lambda w, *_: setattr(w, "text_size", (w.width - dp(24), None)))
    lb.padding_x = dp(12)
    return lb


def with_bg(widget, color):
    from kivy.graphics import Color, Rectangle
    with widget.canvas.before:
        Color(*color)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda *_: setattr(rect, "pos", widget.pos),
                size=lambda *_: setattr(rect, "size", widget.size))


if __name__ == "__main__":
    KnitApp().run()
