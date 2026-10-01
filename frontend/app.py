"""LegalEase - Streamlit frontend.

Run from the project root:
    streamlit run frontend/app.py
"""
import base64
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
import streamlit as st  # noqa: E402

import config  # noqa: E402
from ai_core.generator import (  # noqa: E402
    document_stats,
    format_docx,
    format_html_preview,
    format_pdf,
    parse_terms,
    sanitize_text,
)

st.set_page_config(
    page_title="LegalEase",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DOC_TYPES = [
    "Freelance Work Contract",
    "Non-Disclosure Agreement (NDA)",
    "Employment Contract",
    "Employment Offer Letter",
    "Residential Lease Agreement",
    "Service Agreement",
    "Partnership Agreement",
]
OTHER = "Other..."

# --------------------------------------------------------------------------- #
# Styling
# --------------------------------------------------------------------------- #
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap');
:root { --ink:#0E1729; --panel:#16223A; --line:#27375A; --paper:#FCFCFA; --brass:#C9A24B;
        --text:#E9EDF5; --muted:#9AA6C0; --navy:#101A2E; }
.stApp, [data-testid="stAppViewContainer"] { background: var(--ink); }
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer, [data-testid="stDecoration"] { visibility: hidden; }
.block-container { max-width: 1280px; padding-top: 1.4rem; padding-bottom: 3rem; }
.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button,
.stApp [data-testid="stMarkdownContainer"] { font-family: 'Inter', system-ui, 'Segoe UI', sans-serif; }

.le-top { display:flex; justify-content:space-between; align-items:center;
          padding-bottom:1.1rem; margin-bottom:2rem; border-bottom:1px solid var(--line); }
.le-logo { height:34px; width:auto; display:block; }
.le-chip { display:inline-flex; align-items:center; gap:8px; font-size:.84rem; color:var(--muted); }
.le-chip i { width:8px; height:8px; border-radius:50%; background:#4CAF7A; display:inline-block; }
.le-chip.bad i { background:#E0674F; }

.le-title { font-family:'Source Serif 4', Georgia, 'Times New Roman', serif; font-size:2.5rem;
            font-weight:600; line-height:1.14; letter-spacing:-.01em; color:var(--text); margin:0 0 .8rem 0; }
.le-sub { color:var(--muted); font-size:1.02rem; line-height:1.6; max-width:44ch; margin:0 0 1.6rem 0; }

[data-testid="stBaseButton-primary"], .stButton > button[kind="primary"] {
  background: var(--brass); border: none; color: var(--navy); font-weight: 600; }
[data-testid="stBaseButton-primary"] p, .stButton > button[kind="primary"] p { color: var(--navy); font-weight: 600; }
[data-testid="stBaseButton-primary"]:hover { background:#D6B25F; }
[data-testid="stBaseButton-secondary"] { border-color: var(--line); background: transparent; }
[data-testid="stBaseButton-secondary"]:hover { border-color: var(--brass); color: var(--brass); }

.le-stats { display:flex; gap:26px; color:var(--muted); font-size:.9rem; margin:0 0 .6rem 0; }
.le-stats b { color:var(--text); font-weight:600; }

.stTabs [data-baseweb="tab-list"] { gap:26px; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"] { padding:0 2px; height:44px; color:var(--muted); font-weight:500; background:transparent; }
.stTabs [aria-selected="true"] { color:var(--text); }
.stTabs [data-baseweb="tab-highlight"] { background: var(--brass); }

.paper { background:var(--paper); color:#23262F; border-top:4px solid var(--brass); border-radius:3px;
         padding:54px 64px 58px; max-height:660px; overflow-y:auto;
         box-shadow:0 22px 48px rgba(0,0,0,.45);
         font-family:'Source Serif 4', Georgia, 'Times New Roman', serif; font-size:1.02rem; line-height:1.7; }
.paper p { font-family:inherit; }

.sheet-empty { border:1.5px dashed var(--line); border-radius:3px; padding:54px 52px; min-height:460px; }
.sheet-empty .t { font-family:'Source Serif 4', Georgia, serif; font-size:1.55rem; font-weight:600;
                  color:var(--text); margin-bottom:.4rem; }
.sheet-empty .d { color:var(--muted); margin-bottom:2rem; max-width:40ch; line-height:1.55; }
.step { display:flex; gap:16px; align-items:baseline; margin:0 0 1.1rem 0; color:var(--text); line-height:1.5; }
.step b { font-family:'Source Serif 4', Georgia, serif; font-size:1.3rem; color:var(--brass); min-width:1.2rem; }

.dl-note { color:var(--muted); font-size:.88rem; line-height:1.5; margin:0 0 .7rem 0; min-height:2.6rem; }
.le-fine { color:var(--muted); font-size:.82rem; line-height:1.5; margin-top:1.4rem; }

@media (max-width: 760px) {
  .le-title { font-size:1.9rem; }
  .paper { padding:30px 22px 34px; }
  .sheet-empty { padding:32px 24px; min-height:0; }
}
"""


def squash(text: str, sep: str = "") -> str:
    """Collapse multi-line markup so Markdown never treats it as a code block."""
    return sep.join(line.strip() for line in text.splitlines() if line.strip())


st.markdown(f"<style>{squash(CSS, ' ')}</style>", unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def logo_data_uri(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


@st.cache_data(ttl=5, show_spinner=False)
def backend_online(url: str) -> bool:
    try:
        return requests.get(f"{url}/health", timeout=1.5).ok
    except requests.RequestException:
        return False


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "document"


def format_date(d: date) -> str:
    return f"{d.day} {d:%B %Y}"


def backend_error(exc: Exception) -> str:
    if isinstance(exc, requests.ConnectionError):
        return (
            f"Cannot reach the backend at {config.BACKEND_URL}. "
            "Start it in a second terminal: python -m uvicorn legalEaseAPI.main:app --reload"
        )
    if isinstance(exc, requests.Timeout):
        return "The request timed out. The model may be busy. Try again in a moment."
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        try:
            detail = exc.response.json().get("detail")
        except ValueError:
            detail = None
        if isinstance(detail, list):  # FastAPI validation errors
            detail = "; ".join(str(d.get("msg", d)) for d in detail)
        return str(detail or f"The backend returned HTTP {exc.response.status_code}.")
    return f"Unexpected error: {exc}"


def fill_example():
    st.session_state.doc_choice = "Freelance Work Contract"
    st.session_state.parties = "Jane Doe (Service Provider), TechNova Inc. (Client)"
    st.session_state.terms = (
        "Work must be delivered by May 15, 2025; Payment will be made within 7 days of invoice; "
        "The client retains intellectual property rights; Confidentiality must be maintained at all times"
    )
    st.session_state.eff_date = date.today()


st.session_state.setdefault("generated_text", "")
st.session_state.setdefault("meta", {})

# --------------------------------------------------------------------------- #
# Top bar
# --------------------------------------------------------------------------- #
online = backend_online(config.BACKEND_URL)
logo_uri = logo_data_uri(str(config.WEB_LOGO_PATH))
logo_html = (
    f"<img class='le-logo' src='{logo_uri}' alt='LegalEase'/>"
    if logo_uri
    else "<span class='le-title' style='font-size:1.5rem;margin:0'>LegalEase</span>"
)
chip_cls, chip_txt = ("", "Backend online") if online else ("bad", "Backend offline")
st.markdown(
    squash(
        f"""
        <div class='le-top'>{logo_html}
        <span class='le-chip {chip_cls}'><i></i>{chip_txt}</span></div>
        """
    ),
    unsafe_allow_html=True,
)

left, right = st.columns([5, 6], gap="large")

# --------------------------------------------------------------------------- #
# Left: brief + form
# --------------------------------------------------------------------------- #
with left:
    st.markdown(
        squash(
            """
            <div class='le-title'>Legal documents, drafted in minutes</div>
            <p class='le-sub'>Name the parties and list your terms. LegalEase writes the first draft,
            you edit it, then download it as PDF, Word or plain text.</p>
            """
        ),
        unsafe_allow_html=True,
    )

    if not online:
        st.warning(
            "The backend is not running. In a second terminal, run: "
            "`python -m uvicorn legalEaseAPI.main:app --reload`"
        )

    choice = st.selectbox(
        "Document type",
        DOC_TYPES + [OTHER],
        index=None,
        placeholder="Choose a document type",
        key="doc_choice",
    )
    if choice == OTHER:
        custom_type = st.text_input(
            "Document name", placeholder="e.g. Consulting Agreement", key="custom_type"
        )
    else:
        custom_type = ""

    parties = st.text_area(
        "Parties",
        height=92,
        placeholder="Jane Doe (Service Provider), TechNova Inc. (Client)",
        help="Who is involved, and in what role.",
        key="parties",
    )
    terms = st.text_area(
        "Terms and conditions",
        height=170,
        placeholder="Payment within 7 days of invoice; Work delivered by May 15; Either party may end the contract with 15 days notice",
        key="terms",
    )
    n_terms = len(parse_terms(terms))
    st.caption(
        f"{n_terms} term{'s' if n_terms != 1 else ''} found."
        if n_terms
        else "Separate each term with a semicolon. Leave empty to get standard clauses."
    )
    eff_date = st.date_input("Effective date", value=date.today(), format="DD/MM/YYYY", key="eff_date")

    b1, b2 = st.columns([3, 2])
    generate = b1.button("Generate document", type="primary", key="generate")
    b2.button("Use example", on_click=fill_example, key="example")

    if generate:
        doc_type = (custom_type if choice == OTHER else (choice or "")).strip()
        if not doc_type or not parties.strip():
            st.warning("Choose a document type and name the parties to continue.")
        else:
            try:
                with st.spinner("Drafting your document..."):
                    response = requests.post(
                        f"{config.BACKEND_URL}/generate",
                        json={
                            "document_type": doc_type,
                            "parties": parties,
                            "terms": terms,
                            "dates": format_date(eff_date),
                        },
                        timeout=config.GEMINI_TIMEOUT_SECONDS * (config.GEMINI_MAX_RETRIES + 2),
                    )
                    response.raise_for_status()
                text = sanitize_text(response.json()["document"])
                st.session_state.generated_text = text
                st.session_state.editor_text = text
                st.session_state.meta = {
                    "document_type": doc_type,
                    "parties": parties.strip(),
                    "terms": terms.strip(),
                    "dates": format_date(eff_date),
                }
                st.success("Draft ready. Review it on the right.")
            except (requests.RequestException, KeyError, ValueError) as exc:
                st.error(backend_error(exc))

# --------------------------------------------------------------------------- #
# Right: paper preview / edit / download
# --------------------------------------------------------------------------- #
with right:
    if not st.session_state.generated_text:
        st.markdown(
            squash(
                """
                <div class='sheet-empty'>
                <div class='t'>Your draft will appear here</div>
                <div class='d'>It opens as a paper sheet you can read, edit and download.</div>
                <div class='step'><b>1</b><span>Choose a document type and name the parties.</span></div>
                <div class='step'><b>2</b><span>Add your terms, separated by semicolons.</span></div>
                <div class='step'><b>3</b><span>Generate the draft, then edit and download it.</span></div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )
    else:
        text = st.session_state.get("editor_text", st.session_state.generated_text)
        meta = st.session_state.meta or {}
        doc_type = meta.get("document_type") or "Legal Document"
        stats = document_stats(text)

        st.markdown(
            squash(
                f"""
                <div class='le-stats'>
                <span><b>{stats['words']:,}</b> words</span>
                <span><b>{stats['sections']}</b> sections</span>
                <span>about <b>{stats['pages']}</b> page{'s' if stats['pages'] != 1 else ''}</span>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

        tab_preview, tab_edit, tab_download = st.tabs(["Preview", "Edit", "Download"])

        with tab_preview:
            st.markdown(
                f"<div class='paper'>{format_html_preview(text, theme='paper')}</div>",
                unsafe_allow_html=True,
            )

        with tab_edit:
            st.text_area(
                "Edit the draft",
                key="editor_text",
                height=560,
                label_visibility="collapsed",
            )
            st.caption("Press Ctrl+Enter to apply. Edits carry into the preview and every download.")

        with tab_download:
            base = slugify(doc_type)
            kwargs = dict(
                terms=meta.get("terms", ""),
                parties=meta.get("parties", ""),
                effective_date=meta.get("dates", ""),
            )
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("<p class='dl-note'>Logo and footer on every page. Ready to sign or send.</p>", unsafe_allow_html=True)
                st.download_button(
                    "Download PDF",
                    data=format_pdf(text, doc_type, **kwargs),
                    file_name=f"{base}.pdf",
                    mime="application/pdf",
                )
            with c2:
                st.markdown("<p class='dl-note'>Editable in Word, with a table of key terms.</p>", unsafe_allow_html=True)
                st.download_button(
                    "Download Word",
                    data=format_docx(text, doc_type, **kwargs),
                    file_name=f"{base}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            with c3:
                st.markdown("<p class='dl-note'>Plain text, no formatting.</p>", unsafe_allow_html=True)
                st.download_button(
                    "Download text",
                    data=text,
                    file_name=f"{base}.txt",
                    mime="text/plain",
                )

        st.markdown(
            "<p class='le-fine'>AI-generated drafts are not legal advice. "
            "Have a qualified lawyer review any document before you sign or rely on it.</p>",
            unsafe_allow_html=True,
        )
