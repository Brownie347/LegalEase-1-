"""Drives the real Streamlit script headlessly (backend HTTP calls are mocked)."""
from pathlib import Path

import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "frontend" / "app.py")
DOC = "Freelance Work Contract\n\n1. Services:\n\nThe provider shall deliver the work by the agreed date, in full."


class FakeResp:
    def __init__(self, payload=None, status=200):
        self._payload, self.status_code = payload or {}, status
        self.ok = status < 400

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


def new_app(monkeypatch, post=None, online=True):
    st.cache_data.clear()  # backend_online() is cached for a few seconds
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp({"status": "ok"}, 200 if online else 500))
    if post:
        monkeypatch.setattr(requests, "post", post)
    at = AppTest.from_file(APP, default_timeout=30)
    return at.run()


def fill(at):
    at.selectbox(key="doc_choice").select("Freelance Work Contract")
    at.text_area(key="parties").set_value("Jane Doe (Provider), TechNova (Client)")
    at.text_area(key="terms").set_value("Payment in 7 days; Work due May 15")


def page_text(at):
    return " ".join(m.value for m in at.markdown)


def test_initial_state_shows_empty_sheet(monkeypatch):
    at = new_app(monkeypatch)
    assert not at.exception
    assert "Your draft will appear here" in page_text(at)
    assert "Backend online" in page_text(at)


def test_offline_backend_is_flagged(monkeypatch):
    at = new_app(monkeypatch, online=False)
    assert "Backend offline" in page_text(at)
    assert any("backend is not running" in w.value for w in at.warning)


def test_example_button_fills_form(monkeypatch):
    at = new_app(monkeypatch)
    at.button(key="example").click().run()
    assert at.session_state["doc_choice"] == "Freelance Work Contract"
    assert "TechNova" in at.session_state["parties"]


def test_generate_edit_and_download(monkeypatch):
    sent = {}

    def fake_post(url, json, timeout):
        sent.update(url=url, json=json)
        return FakeResp({"document": DOC})

    at = new_app(monkeypatch, post=fake_post)
    fill(at)
    at.button(key="generate").click().run()
    assert not at.exception
    assert sent["url"].endswith("/generate")
    assert sent["json"]["document_type"] == "Freelance Work Contract"
    assert sent["json"]["parties"].startswith("Jane Doe")
    assert any("Draft ready" in s.value for s in at.success)
    assert "paper" in page_text(at) and "Freelance Work Contract" in page_text(at)

    at.text_area(key="editor_text").set_value("I AM EDITING\n\n" + DOC).run()
    assert not at.exception
    assert "I AM EDITING" in page_text(at)


def test_custom_document_type(monkeypatch):
    sent = {}

    def fake_post(url, json, timeout):
        sent.update(json=json)
        return FakeResp({"document": DOC})

    at = new_app(monkeypatch, post=fake_post)
    at.selectbox(key="doc_choice").select("Other...").run()
    at.text_input(key="custom_type").set_value("Consulting Agreement")
    at.text_area(key="parties").set_value("A (Consultant), B (Client)")
    at.button(key="generate").click().run()
    assert sent["json"]["document_type"] == "Consulting Agreement"


def test_backend_down_shows_friendly_error(monkeypatch):
    def fake_post(*a, **k):
        raise requests.ConnectionError("refused")

    at = new_app(monkeypatch, post=fake_post)
    fill(at)
    at.button(key="generate").click().run()
    assert not at.exception
    assert any("Cannot reach the backend" in e.value for e in at.error)


def test_backend_error_detail_is_shown(monkeypatch):
    at = new_app(
        monkeypatch, post=lambda *a, **k: FakeResp({"detail": "GEMINI_API_KEY is not set"}, status=500)
    )
    fill(at)
    at.button(key="generate").click().run()
    assert any("GEMINI_API_KEY is not set" in e.value for e in at.error)


def test_requires_type_and_parties(monkeypatch):
    at = new_app(monkeypatch)
    at.button(key="generate").click().run()
    assert any("Choose a document type" in w.value for w in at.warning)
