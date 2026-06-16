# -*- coding: utf-8 -*-
"""Мобильное приложение «Вязальное производство» (Android, Kivy).

Полный функционал v2:
  • вход по пользователям (логин/пароль, права как в программе);
  • чтение: Аналитика, План, Доска, Факт, Справочники;
  • запись: ввод факта с телефона (если есть право edit_fact).

Сеть — в фоновом потоке, UI обновляется через Clock. Адрес/ключ/логин
сохраняются в settings.json (user_data_dir).
"""
import os
import json
import threading
import datetime

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
from kivy.uix.popup import Popup

from api import Api, ApiError

# Сканер штрих-кодов (встроенная камера). Импорт «мягкий» + диагностика:
# при недоступности показываем точную причину, чтобы понять, что чинить.
CAMERA_ERR = ""
try:
    from pyzbar.pyzbar import ZBarSymbol
except Exception as e:
    CAMERA_ERR = f"pyzbar: {type(e).__name__}: {e}"
try:
    from kivy_garden.zbarcam import ZBarCam
except Exception as e:
    CAMERA_ERR = (CAMERA_ERR + " | " if CAMERA_ERR else "") + \
        f"zbarcam: {type(e).__name__}: {e}"
HAS_CAMERA = (CAMERA_ERR == "")

BG = (0.07, 0.08, 0.10, 1)
CARD = (0.13, 0.15, 0.18, 1)
ACCENT = (0.20, 0.55, 0.90, 1)
DIMBTN = (0.20, 0.22, 0.25, 1)
TXT = (0.92, 0.94, 0.96, 1)
MUT = (0.62, 0.66, 0.72, 1)
GREEN = (0.20, 0.65, 0.35, 1)
RED = (0.80, 0.30, 0.30, 1)


def with_bg(widget, color):
    from kivy.graphics import Color, Rectangle
    with widget.canvas.before:
        Color(*color)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda *_: setattr(rect, "pos", widget.pos),
                size=lambda *_: setattr(rect, "size", widget.size))


def _row(label, value, big=False):
    b = BoxLayout(size_hint_y=None, height=dp(38 if not big else 56), padding=(dp(12), 0))
    b.add_widget(Label(text=str(label), color=MUT, halign="left", valign="middle",
                       font_size=dp(15), text_size=(dp(190), None)))
    b.add_widget(Label(text=str(value), color=TXT, halign="right", valign="middle",
                       font_size=dp(24 if big else 16), bold=big,
                       text_size=(dp(150), None)))
    return b


def _header(text):
    lb = Label(text=str(text), color=ACCENT, bold=True, size_hint_y=None, height=dp(34),
               halign="left", valign="middle", font_size=dp(15))
    lb.bind(size=lambda w, *_: setattr(w, "text_size", (w.width - dp(24), None)))
    return lb


def _task_card(title, sub, on_press=None):
    card = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(58),
                     padding=(dp(12), dp(6)), spacing=dp(2))
    with_bg(card, CARD)
    t = Label(text=title, color=TXT, halign="left", valign="middle", font_size=dp(15),
              size_hint_y=None, height=dp(24))
    t.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, None)))
    s = Label(text=sub, color=MUT, halign="left", valign="middle", font_size=dp(13),
              size_hint_y=None, height=dp(20))
    s.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, None)))
    card.add_widget(t)
    card.add_widget(s)
    if on_press:
        btn = Button(background_color=(0, 0, 0, 0), on_release=lambda *_: on_press())
        wrap = BoxLayout(size_hint_y=None, height=dp(58))
        wrap.add_widget(card)
        card.add_widget(btn)
    return card


class KnitApp(App):
    def build(self):
        self.title = "Вязальное производство"
        self.api = Api()
        self.period = None
        self.periods = []
        self.view = "an"
        self._load_settings()

        self.root_box = BoxLayout(orientation="vertical")
        with_bg(self.root_box, BG)
        self._build_login()
        return self.root_box

    # ── настройки ───────────────────────────────────────────────────────────
    def _settings_path(self):
        return os.path.join(self.user_data_dir, "settings.json")

    def _load_settings(self):
        self._cfg = {"url": "", "key": "", "user": ""}
        try:
            with open(self._settings_path(), encoding="utf-8") as f:
                self._cfg.update(json.load(f))
        except Exception:
            pass

    def _save_settings(self):
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(self._cfg, f)
        except Exception:
            pass

    # ── экран входа ─────────────────────────────────────────────────────────
    def _build_login(self):
        self.root_box.clear_widgets()
        box = GridLayout(cols=1, spacing=dp(10), padding=dp(20),
                         size_hint=(1, None), pos_hint={"top": 1})
        box.bind(minimum_height=box.setter("height"))
        box.add_widget(Label(text="Вход", color=TXT, font_size=dp(26), bold=True,
                             size_hint_y=None, height=dp(50)))
        self.url_in = TextInput(text=self._cfg.get("url", ""), hint_text="http://IP:8765",
                                multiline=False, size_hint_y=None, height=dp(46),
                                write_tab=False)
        self.key_in = TextInput(text=self._cfg.get("key", ""), hint_text="ключ сервера (если задан)",
                                multiline=False, size_hint_y=None, height=dp(46), write_tab=False)
        self.user_in = TextInput(text=self._cfg.get("user", ""), hint_text="логin",
                                 multiline=False, size_hint_y=None, height=dp(46), write_tab=False)
        self.pw_in = TextInput(hint_text="пароль", password=True, multiline=False,
                               size_hint_y=None, height=dp(46), write_tab=False)
        for w in (self.url_in, self.key_in, self.user_in, self.pw_in):
            box.add_widget(w)
        self.login_btn = Button(text="Войти", background_color=ACCENT, color=(1, 1, 1, 1),
                                size_hint_y=None, height=dp(50),
                                on_release=lambda *_: self.do_login())
        box.add_widget(self.login_btn)
        self.login_status = Label(text="", color=MUT, size_hint_y=None, height=dp(40),
                                  font_size=dp(14))
        box.add_widget(self.login_status)
        self.root_box.add_widget(box)

    def do_login(self):
        url = self.url_in.text.strip()
        key = self.key_in.text.strip()
        user = self.user_in.text.strip()
        pw = self.pw_in.text
        if not url or not user:
            self.login_status.text = "Укажите адрес сервера и логин."
            return
        self.api = Api(url, key)
        self.login_status.text = "Вход…"

        def work():
            try:
                r = self.api.login(user, pw)
                err = None if r.get("ok") else r.get("error", "ошибка входа")
            except ApiError as e:
                r, err = None, str(e)
            Clock.schedule_once(lambda *_: self._after_login(user, err), 0)
        threading.Thread(target=work, daemon=True).start()

    def _after_login(self, user, err):
        if err:
            self.login_status.text = f"Ошибка: {err}"
            return
        self._cfg.update({"url": self.api.base_url, "key": self.api.key, "user": user})
        self._save_settings()
        self._build_main()

    # ── основной экран ──────────────────────────────────────────────────────
    def _build_main(self):
        self.root_box.clear_widgets()

        top = GridLayout(cols=1, size_hint_y=None, height=dp(96), padding=dp(8),
                         spacing=dp(6))
        with_bg(top, CARD)
        line = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        who = self.api.full_name or self._cfg.get("user", "")
        line.add_widget(Label(text=f"{who} · {self.api.role}", color=MUT,
                              halign="left", valign="middle", font_size=dp(13),
                              text_size=(dp(220), None)))
        line.add_widget(Button(text="Выход", size_hint_x=None, width=dp(90),
                               background_color=DIMBTN, on_release=lambda *_: self.do_logout()))
        top.add_widget(line)
        self.period_sp = Spinner(text="период", values=[], size_hint_y=None, height=dp(40))
        self.period_sp.bind(text=lambda *_: self.on_period())
        top.add_widget(self.period_sp)
        self.root_box.add_widget(top)

        tabs = GridLayout(cols=3, size_hint_y=None, height=dp(86), spacing=dp(2))
        self.tab_btns = {}
        for key, lbl in [("scan", "Скан"), ("an", "Аналитика"), ("plan", "План"),
                         ("board", "Доска"), ("fact", "Факт"), ("ref", "Справ.")]:
            b = Button(text=lbl, font_size=dp(13),
                       on_release=lambda _w, k=key: self.show(k))
            self.tab_btns[key] = b
            tabs.add_widget(b)
        self.root_box.add_widget(tabs)

        self.status = Label(text="", color=MUT, size_hint_y=None, height=dp(26),
                            font_size=dp(13))
        self.root_box.add_widget(self.status)

        self.scroll = ScrollView()
        self.content = GridLayout(cols=1, size_hint_y=None, spacing=dp(6), padding=(0, dp(4)))
        self.content.bind(minimum_height=self.content.setter("height"))
        self.scroll.add_widget(self.content)
        self.root_box.add_widget(self.scroll)

        self.show("an")
        self._bg(self.api.periods, self._on_periods)

    def do_logout(self):
        self.api.logout()
        self._build_login()

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
        if self.period_sp.text and self.period_sp.text != self.period \
                and self.period_sp.text in self.period_sp.values:
            self.period = self.period_sp.text
            self.refresh()

    def show(self, view):
        self.view = view
        for k, b in self.tab_btns.items():
            b.background_color = ACCENT if k == view else DIMBTN
        self.refresh()

    def refresh(self):
        if self.view == "scan":
            return self._render_scan()
        if not self.period:
            return
        self._set_status("Загрузка…")
        p = self.period
        v = self.view
        fn = {"an": lambda: self.api.analytics(p), "plan": lambda: self.api.plan(p),
              "board": lambda: self.api.board(p), "fact": lambda: self.api.fact(p),
              "ref": lambda: self.api.refs(self._ref_kind())}[v]
        render = {"an": self._render_analytics, "plan": self._render_plan,
                  "board": self._render_board, "fact": self._render_fact,
                  "ref": self._render_refs}[v]
        self._bg(fn, render)

    # ── рендеры ───────────────────────────────────────────────────────────
    def _render_analytics(self, a, err):
        self.content.clear_widgets()
        if err:
            return self._set_status(f"Ошибка: {err}")
        self._set_status(f"Период: {a['период']}")
        self.content.add_widget(_row("Выполнение", f"{a['выполнение_%']} %", big=True))
        for lbl, k in [("План, пар", "план_пар"), ("Факт, пар", "факт_пар"),
                       ("Остаток, пар", "остаток_пар"), ("Заданий", "заданий"),
                       ("Не назначено", "не_назначено"),
                       ("Машин активно", "машин_активно"),
                       ("Машин задействовано", "машин_задействовано"),
                       ("Средняя загрузка, пар", "средняя_загрузка_пар")]:
            self.content.add_widget(_row(lbl, a.get(k, "—")))
        for r in (a.get("топ_отставаний") or [])[:1]:
            self.content.add_widget(_header("Топ отставаний"))
            break
        for r in (a.get("топ_отставаний") or []):
            self.content.add_widget(_row(f"{r['art']} {r.get('color','')}".strip(),
                                         f"−{r['остаток']}"))

    def _render_plan(self, rows, err):
        self.content.clear_widgets()
        if err:
            return self._set_status(f"Ошибка: {err}")
        self._set_status(f"Заданий: {len(rows)}")
        for r in rows[:400]:
            m = f"маш {r['machine']}" if r["machine"] is not None else "не назначено"
            sub = f"РЦ {r['rc']} · {m} · план {r['qty_plan']} · факт {r['done']}"
            self.content.add_widget(_task_card(
                f"{r['art']} {r['color']} {r['sz']}".strip(), sub))
        if len(rows) > 400:
            self.content.add_widget(_row("…", f"показаны первые 400 из {len(rows)}"))

    def _render_board(self, machines, err):
        self.content.clear_widgets()
        if err:
            return self._set_status(f"Ошибка: {err}")
        self._set_status(f"Машин: {len(machines)}")
        for m in machines:
            self.content.add_widget(_header(f"Машина {m['machine']} · РЦ {m['rc']}"))
            for i, t in enumerate(m["tasks"], 1):
                sub = f"план {t['qty_plan']} · факт {t['done']} · ост {t['остаток']}"
                self.content.add_widget(_task_card(
                    f"{i}. {t['art']} {t['color']} {t['sz']}".strip(), sub))

    def _render_fact(self, rows, err):
        self.content.clear_widgets()
        if err:
            return self._set_status(f"Ошибка: {err}")
        can_edit = self.api.can("edit_fact")
        self._set_status(("Факт — нажмите задание для ввода" if can_edit
                          else "Факт (только просмотр)"))
        for r in rows[:400]:
            sub = f"план {r['qty_plan']} · факт {r['done']} · ост {r['остаток']} · {r['процент']}%"
            cb = (lambda rr=r: self._open_fact_entry(rr)) if can_edit else None
            self.content.add_widget(_task_card(
                f"{r['art']} {r['color']} {r['sz']}".strip(), sub, on_press=cb))

    def _ref_kind(self):
        return getattr(self, "_refkind", "articles")

    def _render_refs(self, rows, err):
        self.content.clear_widgets()
        if err:
            return self._set_status(f"Ошибка: {err}")
        switch = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        for kind, lbl in [("articles", "Артикулы"), ("machines", "Машины")]:
            switch.add_widget(Button(
                text=lbl, font_size=dp(13),
                background_color=ACCENT if self._ref_kind() == kind else DIMBTN,
                on_release=lambda _w, k=kind: self._set_ref_kind(k)))
        self.content.add_widget(switch)
        self._set_status(f"Записей: {len(rows)}")
        if self._ref_kind() == "machines":
            for r in rows:
                self.content.add_widget(_row(f"Машина {r['number']}",
                                             f"РЦ {r['rc']} · {r['status']}"))
        else:
            for r in rows[:500]:
                self.content.add_widget(_task_card(
                    f"{r['art']} {r['color']} {r['sz']}".strip(),
                    f"РЦ {r['rc']} · {r.get('type','')}"))

    def _set_ref_kind(self, kind):
        self._refkind = kind
        self.refresh()

    # ── скан паспорта мешка ─────────────────────────────────────────────────
    def _render_scan(self):
        self.content.clear_widgets()
        self._set_status("Скан паспорта мешка")
        box = GridLayout(cols=1, size_hint_y=None, spacing=dp(10), padding=dp(8))
        box.bind(minimum_height=box.setter("height"))
        box.add_widget(Label(text="Отсканируйте штрих-код паспорта мешка камерой "
                            "или введите код вручную.", color=MUT, font_size=dp(14),
                            size_hint_y=None, height=dp(46),
                            text_size=(dp(320), None), halign="left"))
        cam_btn = Button(text="📷 Сканировать камерой", background_color=ACCENT,
                         color=(1, 1, 1, 1), size_hint_y=None, height=dp(54),
                         on_release=lambda *_: self._start_camera())
        box.add_widget(cam_btn)
        self.code_in = TextInput(hint_text="код паспорта (вручную)", multiline=False,
                                 size_hint_y=None, height=dp(48), write_tab=False)
        box.add_widget(self.code_in)
        box.add_widget(Button(text="Найти по коду", background_color=DIMBTN,
                              size_hint_y=None, height=dp(48),
                              on_release=lambda *_: self._lookup(self.code_in.text.strip())))
        self.scan_msg = Label(text=("" if HAS_CAMERA else
                                    "Камера недоступна: " + CAMERA_ERR),
                              color=MUT, font_size=dp(12), size_hint_y=None, height=dp(80),
                              text_size=(dp(320), None), halign="left")
        box.add_widget(self.scan_msg)
        self.content.add_widget(box)

    def _start_camera(self):
        if not HAS_CAMERA:
            self.scan_msg.text = "Камера недоступна: " + CAMERA_ERR
            return
        try:
            # QR — основной формат паспортов; меньше типов = быстрее распознавание
            zbarcam = ZBarCam(code_types=[ZBarSymbol.QRCODE, ZBarSymbol.CODE39,
                                          ZBarSymbol.CODE128])
        except Exception as e:
            self.scan_msg.text = f"Не удалось включить камеру: {e}"
            return

        # Понизить разрешение камеры — главное средство от зависаний.
        def _lower_res(*_):
            try:
                xc = getattr(zbarcam, "xcamera", None)
                if xc is None and hasattr(zbarcam, "ids"):
                    xc = zbarcam.ids.get("xcamera")
                if xc is not None:
                    xc.resolution = (640, 480)
                    xc.allow_stretch = True
            except Exception:
                pass
        Clock.schedule_once(_lower_res, 0)

        wrap = BoxLayout(orientation="vertical")
        wrap.add_widget(zbarcam)
        popup = Popup(title="Наведите на QR/штрих-код", content=wrap, size_hint=(0.95, 0.85))

        # защита: не реагировать на самый первый кадр/старый символ и сработать 1 раз
        self._scan_done = False
        self._scan_armed = False
        Clock.schedule_once(lambda *_: setattr(self, "_scan_armed", True), 0.8)

        def on_symbols(_inst, symbols):
            if not symbols or not self._scan_armed or self._scan_done:
                return
            self._scan_done = True
            code = symbols[0].data.decode("utf-8", "ignore")
            try:
                zbarcam.stop()
                zbarcam.xcamera.play = False
            except Exception:
                pass
            popup.dismiss()
            self._lookup(code)
        zbarcam.bind(symbols=on_symbols)

        def _close(*_):
            try:
                zbarcam.stop()
                zbarcam.xcamera.play = False
            except Exception:
                pass
            popup.dismiss()
        wrap.add_widget(Button(text="Отмена", size_hint_y=None, height=dp(48),
                               background_color=DIMBTN, on_release=_close))
        popup.bind(on_dismiss=lambda *_: _close())
        popup.open()

    def _lookup(self, code):
        code = (code or "").strip()
        if not code:
            return
        self._set_status(f"Поиск паспорта {code}…")
        self._bg(lambda: self.api.passport(code, self.period), self._on_passport)

    def _on_passport(self, p, err):
        if err:
            return self._set_status(f"Ошибка: {err}")
        if not p.get("ok"):
            return self._set_status(p.get("error", "паспорт не найден"))
        self._open_passport_fact(p)

    def _open_passport_fact(self, p):
        can_edit = self.api.can("edit_fact")
        c = GridLayout(cols=1, spacing=dp(6), padding=dp(12))
        c.add_widget(Label(text=f"{p['art']} {p['color']} {p['sz']}".strip(), color=TXT,
                           font_size=dp(17), bold=True, size_hint_y=None, height=dp(28)))
        info = (f"Маш {p['machine']} · РЦ {p['rc']} · {p['fact_date']} · {p['смена']} · "
                f"план {p['plan_qty']}")
        c.add_widget(Label(text=info, color=MUT, font_size=dp(13),
                           size_hint_y=None, height=dp(22)))
        c.add_widget(Label(text=f"Исполнитель: {self.api.full_name}", color=MUT,
                           font_size=dp(13), size_hint_y=None, height=dp(22)))
        c.add_widget(Label(text="Факт 1 сорт (в план):", color=TXT, font_size=dp(14),
                           size_hint_y=None, height=dp(22), halign="left",
                           text_size=(dp(300), None)))
        g1 = TextInput(text=str(p.get("fact1") or ""), input_filter="int",
                       multiline=False, size_hint_y=None, height=dp(44), write_tab=False)
        c.add_widget(g1)
        c.add_widget(Label(text="Факт 2 сорт (побочный, в 1С):", color=TXT, font_size=dp(14),
                           size_hint_y=None, height=dp(22), halign="left",
                           text_size=(dp(300), None)))
        g2 = TextInput(text=str(p.get("fact2") or ""), input_filter="int",
                       multiline=False, size_hint_y=None, height=dp(44), write_tab=False)
        c.add_widget(g2)
        msg = Label(text=("" if can_edit else "Нет права на ввод факта"),
                    color=MUT, font_size=dp(13), size_hint_y=None, height=dp(24))
        c.add_widget(msg)
        btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        save_b = Button(text="Сохранить", background_color=GREEN,
                        disabled=not can_edit)
        cancel_b = Button(text="Закрыть", background_color=DIMBTN)
        btns.add_widget(save_b)
        btns.add_widget(cancel_b)
        c.add_widget(btns)
        popup = Popup(title=f"Паспорт {p['code']}", content=c, size_hint=(0.92, None),
                      height=dp(460))

        def save(*_):
            msg.text = "Сохранение…"

            def work():
                try:
                    res = self.api.save_passport_fact(p["code"], g1.text or 0, g2.text or 0)
                    err = None if res.get("ok") else res.get("error", "ошибка")
                except ApiError as e:
                    err = str(e)
                Clock.schedule_once(lambda *_: done(err), 0)

            def done(err):
                if err:
                    msg.text = f"Ошибка: {err}"
                else:
                    popup.dismiss()
                    self._set_status(f"Сохранено: {p['art']} {p['color']} {p['sz']}".strip())
            threading.Thread(target=work, daemon=True).start()

        save_b.bind(on_release=save)
        cancel_b.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    # ── ввод факта ──────────────────────────────────────────────────────────
    def _open_fact_entry(self, r):
        content = GridLayout(cols=1, spacing=dp(8), padding=dp(12))
        content.add_widget(Label(text=f"{r['art']} {r['color']} {r['sz']}".strip(),
                                 color=TXT, font_size=dp(16), size_hint_y=None, height=dp(30)))
        content.add_widget(Label(text=f"План {r['qty_plan']} · уже факт {r['done']}",
                                 color=MUT, font_size=dp(13), size_hint_y=None, height=dp(22)))
        date_in = TextInput(text=datetime.date.today().isoformat(),
                            hint_text="дата ГГГГ-ММ-ДД", multiline=False,
                            size_hint_y=None, height=dp(44), write_tab=False)
        day_in = TextInput(hint_text="день (пар)", input_filter="int",
                          multiline=False, size_hint_y=None, height=dp(44), write_tab=False)
        night_in = TextInput(hint_text="ночь (пар)", input_filter="int",
                            multiline=False, size_hint_y=None, height=dp(44), write_tab=False)
        content.add_widget(date_in)
        content.add_widget(day_in)
        content.add_widget(night_in)
        msg = Label(text="", color=MUT, font_size=dp(13), size_hint_y=None, height=dp(24))
        content.add_widget(msg)
        btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        save_b = Button(text="Сохранить", background_color=GREEN)
        cancel_b = Button(text="Отмена", background_color=DIMBTN)
        btns.add_widget(save_b)
        btns.add_widget(cancel_b)
        content.add_widget(btns)

        popup = Popup(title="Ввод факта", content=content, size_hint=(0.9, None),
                      height=dp(420))

        def save(*_):
            msg.text = "Сохранение…"

            def work():
                try:
                    res = self.api.save_fact(r["id"], date_in.text.strip(),
                                             day_in.text or 0, night_in.text or 0)
                    err = None if res.get("ok") else res.get("error", "ошибка")
                except ApiError as e:
                    err = str(e)
                Clock.schedule_once(lambda *_: done(err), 0)

            def done(err):
                if err:
                    msg.text = f"Ошибка: {err}"
                else:
                    popup.dismiss()
                    self.refresh()
            threading.Thread(target=work, daemon=True).start()

        save_b.bind(on_release=save)
        cancel_b.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    # ── утилиты ───────────────────────────────────────────────────────────
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
        if hasattr(self, "status"):
            self.status.text = t


if __name__ == "__main__":
    KnitApp().run()
