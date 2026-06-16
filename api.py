# -*- coding: utf-8 -*-
"""Сетевой слой мобильного клиента — общается с mobile_server.py.

Без Kivy, только стандартная библиотека (тестируется отдельно).
"""
import json
import urllib.request
import urllib.parse
import urllib.error


class ApiError(Exception):
    pass


class Api:
    def __init__(self, base_url="", key=""):
        self.base_url = (base_url or "").rstrip("/")
        self.key = key or ""
        self.token = ""
        self.caps = []
        self.full_name = ""
        self.role = ""

    # ── низкий уровень ──────────────────────────────────────────────────────
    def _url(self, path, params=None):
        params = dict(params or {})
        if self.key:
            params["key"] = self.key
        qs = ("?" + urllib.parse.urlencode(params, encoding="utf-8")) if params else ""
        return self.base_url + path + qs

    def _open(self, req):
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                raise ApiError(f"HTTP {e.code}")
        except Exception as e:
            raise ApiError(f"нет связи с сервером: {e}")

    def _get(self, path, params=None):
        if not self.base_url:
            raise ApiError("не задан адрес сервера")
        data = self._open(urllib.request.Request(self._url(path, params)))
        if isinstance(data, dict) and data.get("error"):
            raise ApiError(data["error"])
        return data

    def _post(self, path, payload):
        if not self.base_url:
            raise ApiError("не задан адрес сервера")
        body = dict(payload or {})
        if self.token:
            body.setdefault("token", self.token)
        req = urllib.request.Request(
            self._url(path), data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        return self._open(req)

    # ── авторизация ─────────────────────────────────────────────────────────
    def login(self, username, password):
        r = self._post("/api/login", {"username": username, "password": password})
        if r.get("ok"):
            self.token = r.get("token", "")
            self.caps = r.get("caps", [])
            self.full_name = r.get("full_name", "")
            self.role = r.get("role", "")
        return r

    def can(self, cap):
        return cap in self.caps

    def logout(self):
        self.token = ""
        self.caps = []
        self.full_name = ""
        self.role = ""

    # ── чтение ──────────────────────────────────────────────────────────────
    def health(self):        return self._get("/api/health")
    def periods(self):       return self._get("/api/periods")
    def analytics(self, p):  return self._get("/api/analytics", {"period": p})
    def machine_load(self, p): return self._get("/api/machine_load", {"period": p})
    def plan(self, p):       return self._get("/api/plan", {"period": p})
    def board(self, p):      return self._get("/api/board", {"period": p})
    def fact(self, p):       return self._get("/api/fact", {"period": p})
    def refs(self, kind):    return self._get("/api/refs", {"type": kind})

    def passport(self, code, period=None):
        params = {"code": code}
        if period:
            params["period"] = period
        return self._get("/api/passport", params)

    def save_passport_fact(self, code, grade1, grade2):
        return self._post("/api/passport_fact", {
            "code": code, "grade1": grade1, "grade2": grade2})

    # ── запись ──────────────────────────────────────────────────────────────
    def save_fact(self, plan_item_id, fact_date, qty_day, qty_night):
        return self._post("/api/fact", {
            "plan_item_id": plan_item_id, "fact_date": fact_date,
            "qty_day": qty_day, "qty_night": qty_night})
