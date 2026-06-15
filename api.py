# -*- coding: utf-8 -*-
"""Сетевой слой мобильного клиента — общается с mobile_server.py.

Без Kivy, только стандартная библиотека, чтобы можно было тестировать отдельно.
"""
import json
import urllib.request
import urllib.parse


class ApiError(Exception):
    pass


class Api:
    def __init__(self, base_url="", key=""):
        self.base_url = (base_url or "").rstrip("/")
        self.key = key or ""

    def _get(self, path, params=None):
        if not self.base_url:
            raise ApiError("не задан адрес сервера")
        params = dict(params or {})
        if self.key:
            params["key"] = self.key
        qs = ("?" + urllib.parse.urlencode(params, encoding="utf-8")) if params else ""
        url = self.base_url + path + qs
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                data = json.loads(e.read().decode("utf-8"))
                raise ApiError(data.get("error", f"HTTP {e.code}"))
            except ApiError:
                raise
            except Exception:
                raise ApiError(f"HTTP {e.code}")
        except Exception as e:
            raise ApiError(f"нет связи с сервером: {e}")
        if isinstance(data, dict) and data.get("error"):
            raise ApiError(data["error"])
        return data

    def health(self):
        return self._get("/api/health")

    def periods(self):
        return self._get("/api/periods")

    def analytics(self, period):
        return self._get("/api/analytics", {"period": period})

    def machine_load(self, period):
        return self._get("/api/machine_load", {"period": period})

    def fact_lag(self, period, limit=20):
        return self._get("/api/fact_lag", {"period": period, "limit": limit})
