"""Invoico UI. Sidebar pages + a local theme switch (no Streamlit hamburger menu)."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import httpx
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.schemas import CATEGORIES  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.fx import convert_docs_to_eur  # noqa: E402

API = settings.api_base
PAGES = ("Overview", "Upload", "Review", "Invoices", "Analyze", "About", "Settings")

st.set_page_config(
    page_title="Invoico",
    page_icon="I",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"Get help": None, "Report a bug": None, "About": None},
)

if "page" not in st.session_state:
    st.session_state.page = "Overview"
if "theme" not in st.session_state:
    st.session_state.theme = "light"
if "analysis" not in st.session_state:
    st.session_state.analysis = None


def theme_css(mode: str) -> str:
    if mode == "dark":
        # Match the sidebar greens so tables/stats don't flash white.
        return """
        <style>
          :root {
            --inv-bg: #0c1210;
            --inv-panel: #14201b;
            --inv-panel-2: #1a2a24;
            --inv-border: #2d4a3e;
            --inv-text: #ecfdf5;
            --inv-muted: #a7f3d0;
            --inv-faint: #86b8a4;
          }

          .stApp, .stApp * { color-scheme: dark; }
          .stApp { background: var(--inv-bg) !important; color: var(--inv-text) !important; }
          [data-testid="stHeader"] { background: rgba(12,18,16,0.95) !important; }
          [data-testid="stSidebar"] {
            background: #0a100e !important;
            border-right: 1px solid var(--inv-border) !important;
          }

          /* Page copy */
          .page-kicker, .page-sub, .stCaption, [data-testid="stCaption"] {
            color: var(--inv-muted) !important; opacity: 1 !important;
          }
          .page-title, h1, h2, h3, h4,
          [data-testid="stMarkdownContainer"] p,
          [data-testid="stMarkdownContainer"] li,
          [data-testid="stMarkdownContainer"] span {
            color: var(--inv-text) !important;
          }

          /* Widget labels were nearly black on dark — force them light */
          label, [data-testid="stWidgetLabel"],
          [data-testid="stWidgetLabel"] p,
          [data-testid="stWidgetLabel"] span,
          .stSelectbox label, .stTextInput label, .stNumberInput label,
          .stTextArea label, .stRadio label, .stCheckbox label,
          [data-baseweb="select"] + div,
          .stMultiSelect label {
            color: var(--inv-muted) !important;
          }

          /* Inputs / selects / text areas */
          .stTextInput input, .stNumberInput input, .stTextArea textarea,
          [data-baseweb="select"] > div,
          [data-baseweb="input"] {
            background-color: var(--inv-panel) !important;
            color: var(--inv-text) !important;
            border-color: var(--inv-border) !important;
            caret-color: var(--inv-text) !important;
          }
          [data-baseweb="popover"], [data-baseweb="menu"],
          ul[role="listbox"], li[role="option"] {
            background-color: var(--inv-panel-2) !important;
            color: var(--inv-text) !important;
          }
          li[role="option"]:hover, li[aria-selected="true"] {
            background-color: #24352e !important;
          }

          /* Metric cards + bordered containers */
          div[data-testid="stMetric"],
          div[data-testid="stVerticalBlockBorderWrapper"],
          div[data-testid="stForm"],
          [data-testid="stExpander"] {
            background: var(--inv-panel) !important;
            border: 1px solid var(--inv-border) !important;
            border-radius: 0.6rem;
          }
          [data-testid="stMetricLabel"],
          [data-testid="stMetricLabel"] p,
          [data-testid="stMetricDelta"] {
            color: var(--inv-muted) !important;
          }
          [data-testid="stMetricValue"],
          [data-testid="stMetricValue"] * {
            color: var(--inv-text) !important;
          }

          /* Custom dark tables (Streamlit's grid stays white no matter what) */
          .inv-table-wrap {
            overflow-x: auto;
            border: 1px solid var(--inv-border);
            border-radius: 0.6rem;
            background: var(--inv-panel);
          }
          table.inv-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.92rem;
            color: var(--inv-text);
          }
          table.inv-table thead th {
            position: sticky; top: 0;
            background: #1a2a24;
            color: var(--inv-muted);
            text-align: left;
            font-weight: 600;
            padding: 0.65rem 0.75rem;
            border-bottom: 1px solid var(--inv-border);
            white-space: nowrap;
          }
          table.inv-table tbody td {
            padding: 0.55rem 0.75rem;
            border-bottom: 1px solid #1f2e28;
            color: var(--inv-text);
            vertical-align: top;
          }
          table.inv-table tbody tr:nth-child(even) td {
            background: rgba(26, 42, 36, 0.55);
          }
          table.inv-table tbody tr:hover td {
            background: #24352e;
          }

          /* Charts on a dark panel */
          [data-testid="stVegaLiteChart"],
          [data-testid="stArrowVegaLiteChart"],
          [data-testid="stVegaLiteChart"] > div,
          .stPlotlyChart {
            background: var(--inv-panel) !important;
            border: 1px solid var(--inv-border) !important;
            border-radius: 0.5rem;
            padding: 0.5rem;
          }
          /* Vega often paints a white canvas — nudge the surrounding frame */
          [data-testid="stVegaLiteChart"] svg,
          [data-testid="stArrowVegaLiteChart"] svg {
            background: transparent !important;
          }

          /* Buttons (secondary / download) */
          .stDownloadButton button,
          button[kind="secondary"] {
            background: var(--inv-panel-2) !important;
            color: var(--inv-text) !important;
            border: 1px solid var(--inv-border) !important;
          }
          button[kind="primary"] {
            background: #6ee7b7 !important;
            color: #0a100e !important;
            border: none !important;
          }

          /* Alerts / info boxes */
          [data-testid="stAlert"] {
            background: var(--inv-panel-2) !important;
            color: var(--inv-text) !important;
            border: 1px solid var(--inv-border) !important;
          }

          /* File uploader */
          [data-testid="stFileUploader"] section,
          [data-testid="stFileUploaderDropzone"] {
            background: var(--inv-panel) !important;
            border-color: var(--inv-border) !important;
            color: var(--inv-text) !important;
          }
          [data-testid="stFileUploader"] * {
            color: var(--inv-muted) !important;
          }

          /* JSON / code blocks on Analyze */
          .stJson, [data-testid="stJson"], pre, code {
            background: var(--inv-panel-2) !important;
            color: var(--inv-text) !important;
          }

          /* Sidebar nav already dark; keep captions readable */
          [data-testid="stSidebar"] .stCaption,
          [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: var(--inv-muted) !important;
          }
        </style>
        """
    return """
    <style>
      .stApp { background: #f4f1ec; color: #1c1917; }
      [data-testid="stHeader"] { background: rgba(244,241,236,0.92); }
      [data-testid="stSidebar"] {
        background: #14261f !important;
        border-right: 1px solid #2d4a3e;
      }
      [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
      [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
      [data-testid="stSidebar"] label,
      [data-testid="stSidebar"] .stCaption {
        color: #ecfdf5 !important;
      }
      .page-kicker, .page-sub { color: #57534e !important; opacity: 1 !important; }
      .page-title { color: #1c1917 !important; }
    </style>
    """


st.markdown(
    theme_css(st.session_state.theme)
    + """
    <style>
      /* Kill the Streamlit menu / deploy / screencast. Keep header for sidebar reopen. */
      #MainMenu, [data-testid="stMainMenu"], [data-testid="stToolbar"],
      .stAppDeployButton, [data-testid="stAppDeployButton"],
      [data-testid="stStatusWidget"], footer {
        display: none !important;
        visibility: hidden !important;
      }

      .invoico-brand {
        font-size: 1.55rem; font-weight: 700; letter-spacing: -0.03em;
        color: #ecfdf5; margin: 0;
      }
      .invoico-tag {
        color: #a7f3d0; font-size: 0.85rem; margin: 0.2rem 0 1rem 0;
      }
      .page-kicker {
        text-transform: uppercase; letter-spacing: 0.08em;
        font-size: 0.72rem; opacity: 0.65; margin-bottom: 0.2rem;
      }
      .page-title {
        font-size: 1.7rem; font-weight: 650; letter-spacing: -0.02em; margin: 0 0 0.3rem 0;
      }
      .page-sub { opacity: 0.78; margin-bottom: 1.1rem; }

      /* Use the width — default Streamlit gutters waste a ton on big monitors */
      .stMain .block-container {
        padding-top: 1.25rem;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
        padding-bottom: 2rem;
        max-width: min(1600px, 96vw);
      }
      @media (min-width: 1400px) {
        .stMain .block-container {
          padding-left: 2rem;
          padding-right: 2rem;
          max-width: min(1700px, 97vw);
        }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def api(method: str, path: str, **kwargs):
    url = f"{API}{path}"
    try:
        with httpx.Client(timeout=300.0) as client:
            r = client.request(method, url, **kwargs)
            r.raise_for_status()
            if not r.content:
                return {}
            ctype = r.headers.get("content-type", "")
            if "csv" in ctype:
                return r.text
            return r.json()
    except httpx.ConnectError:
        st.error(
            f"API is down at `{API}`.\n\n"
            "`uvicorn app.api.main:app --host 127.0.0.1 --port 8000`"
        )
        st.stop()
    except httpx.HTTPStatusError as exc:
        st.error(f"API {exc.response.status_code}: {exc.response.text}")
        return None


def page_header(kicker: str, title: str, subtitle: str) -> None:
    st.markdown(f'<div class="page-kicker">{kicker}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-sub">{subtitle}</div>', unsafe_allow_html=True)


def money(value: float | None, currency: str | None = None) -> str:
    if value is None:
        return "—"
    suffix = f" {currency}" if currency else ""
    return f"{value:,.2f}{suffix}"


def is_dark() -> bool:
    return st.session_state.get("theme") == "dark"


def show_table(df: pd.DataFrame) -> None:
    """Light mode keeps Streamlit's grid; dark mode uses an HTML table that matches the sidebar."""
    if df is None or df.empty:
        st.caption("No rows.")
        return
    if not is_dark():
        st.dataframe(df, use_container_width=True, hide_index=True)
        return

    cols = list(df.columns)
    header = "".join(f"<th>{c}</th>" for c in cols)
    body_rows = []
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            val = row[c]
            if pd.isna(val):
                text = ""
            elif isinstance(val, float):
                text = f"{val:.2f}" if abs(val) < 1e6 else f"{val:,.2f}"
            else:
                text = str(val)
            cells.append(f"<td>{text}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    html = f"""
    <div class="inv-table-wrap">
      <table class="inv-table">
        <thead><tr>{header}</tr></thead>
        <tbody>{''.join(body_rows)}</tbody>
      </table>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def show_bar(series: pd.Series, *, horizontal: bool = False) -> None:
    if not is_dark():
        st.bar_chart(series, horizontal=horizontal, color="#1a5f4a")
        return
    # Altair so the chart background matches the sidebar instead of staying white
    import altair as alt

    chart_df = series.rename("value").rename_axis("label").reset_index()
    if horizontal:
        enc = dict(
            x=alt.X("value:Q", title=None),
            y=alt.Y("label:N", sort="-x", title=None),
        )
    else:
        enc = dict(
            x=alt.X("label:N", title=None, sort=None),
            y=alt.Y("value:Q", title=None),
        )
    chart = (
        alt.Chart(chart_df)
        .mark_bar(color="#6ee7b7", cornerRadiusEnd=3)
        .encode(**enc)
        .properties(height=280)
        .configure(background="#14201b")
        .configure_axis(
            labelColor="#a7f3d0",
            titleColor="#a7f3d0",
            gridColor="#2d4a3e",
            domainColor="#2d4a3e",
            tickColor="#2d4a3e",
        )
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(chart, use_container_width=True)


def docs_frame(docs: list[dict]) -> pd.DataFrame:
    if not docs:
        return pd.DataFrame()
    df = pd.DataFrame(docs)
    for col in ("net_amount", "vat_amount", "vat_rate", "gross_amount"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "issue_date" in df.columns:
        df["issue_date"] = pd.to_datetime(df["issue_date"], errors="coerce")
    return df


def edit_form(doc: dict, form_key: str, *, confirm: bool = False) -> None:
    note_text = doc.get("note") or doc.get("review_reason") or ""
    with st.form(form_key, border=True):
        vendor = st.text_input("Vendor", value=doc.get("vendor") or "")
        invoice_no = st.text_input("Invoice number", value=doc.get("invoice_no") or "")
        c1, c2 = st.columns(2)
        issue_date = c1.text_input("Issue date", value=doc.get("issue_date") or "")
        due_date = c2.text_input("Due date", value=doc.get("due_date") or "")
        currency = st.text_input("Currency", value=doc.get("currency") or "")
        a1, a2, a3, a4 = st.columns(4)
        net_amount = a1.number_input("Net", value=float(doc.get("net_amount") or 0.0), format="%.2f")
        vat_amount = a2.number_input("VAT", value=float(doc.get("vat_amount") or 0.0), format="%.2f")
        vat_rate = a3.number_input("VAT %", value=float(doc.get("vat_rate") or 0.0), format="%.2f")
        gross_amount = a4.number_input("Gross", value=float(doc.get("gross_amount") or 0.0), format="%.2f")
        category = st.selectbox(
            "Category",
            options=list(CATEGORIES),
            index=list(CATEGORIES).index(doc["category"])
            if doc.get("category") in CATEGORIES
            else list(CATEGORIES).index("Other"),
        )
        doc_type = st.selectbox(
            "Type",
            options=["invoice", "receipt", "other"],
            index=["invoice", "receipt", "other"].index(doc.get("doc_type") or "other"),
        )
        note = st.text_area("Note", value=note_text)
        label = "Confirm" if confirm else "Save changes"
        submitted = st.form_submit_button(label, type="primary")

    if submitted:
        payload = {
            "vendor": vendor or None,
            "invoice_no": invoice_no or None,
            "issue_date": issue_date or None,
            "due_date": due_date or None,
            "currency": currency or None,
            "net_amount": net_amount,
            "vat_amount": vat_amount,
            "vat_rate": vat_rate,
            "gross_amount": gross_amount,
            "category": category,
            "doc_type": doc_type,
            "note": note or None,
            "confirm": confirm,
        }
        updated = api("PATCH", f"/documents/{doc['id']}", json=payload)
        if updated:
            st.success("Saved.")
            st.rerun()


def render_overview(docs: list[dict]) -> None:
    page_header(
        "Overview",
        "Spending at a glance",
        "Totals are estimated in EUR so mixed currencies stay comparable.",
    )
    df = docs_frame(docs)
    if df.empty:
        st.info("Nothing in the database yet. Upload a couple of invoices first.")
        return

    usable_docs = [d for d in docs if d.get("status") in ("auto_ok", "needs_review", "confirmed")]
    fx = convert_docs_to_eur(usable_docs)
    pending_n = sum(1 for d in docs if d.get("status") in ("needs_review", "auto_ok", "failed"))

    st.info(fx["disclaimer"])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Gross (EUR est.)", money(fx["gross_eur"], "EUR"), border=True)
    m2.metric("Net (EUR est.)", money(fx["net_eur"], "EUR"), border=True)
    m3.metric("VAT (EUR est.)", money(fx["vat_eur"], "EUR"), border=True)
    m4.metric("Open for review", str(pending_n), border=True)

    native = fx["native_by_currency"]
    if native:
        chips = " · ".join(f"{c}: {v:,.2f}" for c, v in sorted(native.items()))
        st.caption(f"Native totals (unconverted): {chips} · FX file as of **{fx['as_of']}**")
    if fx["skipped"]:
        st.warning(
            f"{len(fx['skipped'])} row(s) skipped — currency not in the static ECB file "
            f"(supported: {', '.join(fx['supported'][:12])}…)."
        )

    # Charts use EUR-converted gross
    eur_rows = []
    for r in fx["converted_rows"]:
        eur_rows.append(
            {
                "category": r.get("category") or "Other",
                "vendor": r.get("vendor") or "Unknown",
                "issue_date": r.get("issue_date"),
                "gross_eur": r.get("amount_eur") or 0.0,
            }
        )
    eur_df = pd.DataFrame(eur_rows)
    if not eur_df.empty and "issue_date" in eur_df.columns:
        eur_df["issue_date"] = pd.to_datetime(eur_df["issue_date"], errors="coerce")

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("**Spend by category (EUR)**")
            by_cat = (
                eur_df.groupby("category")["gross_eur"].sum().fillna(0).sort_values(ascending=False)
                if not eur_df.empty
                else pd.Series(dtype=float)
            )
            if by_cat.empty or by_cat.sum() == 0:
                st.caption("No amounts yet.")
            else:
                show_bar(by_cat, horizontal=True)
                top = by_cat.index[0]
                share = (by_cat.iloc[0] / by_cat.sum() * 100) if by_cat.sum() else 0
                st.caption(f"Largest: **{top}** ({share:.0f}% of EUR spend).")
    with right:
        with st.container(border=True):
            st.markdown("**Top vendors (EUR)**")
            by_vendor = (
                eur_df.groupby("vendor")["gross_eur"]
                .sum()
                .fillna(0)
                .sort_values(ascending=False)
                .head(10)
                if not eur_df.empty
                else pd.Series(dtype=float)
            )
            if by_vendor.empty:
                st.caption("No vendors yet.")
            else:
                show_table(by_vendor.rename("gross_eur").reset_index())

    with st.container(border=True):
        st.markdown("**Monthly spend (EUR)**")
        dated = eur_df.dropna(subset=["issue_date"]).copy() if not eur_df.empty else eur_df
        if dated.empty:
            st.caption("Need issue dates for a monthly chart.")
        else:
            dated["month"] = dated["issue_date"].dt.to_period("M").astype(str)
            show_bar(dated.groupby("month")["gross_eur"].sum().sort_index())

    if st.button("Ask the model to analyze this", type="primary"):
        st.session_state.page = "Analyze"
        st.rerun()


def render_upload() -> None:
    page_header(
        "Upload",
        "Drop invoices & receipts",
        "Extraction runs through Ollama on this machine. Nothing gets uploaded to a cloud API.",
    )
    with st.container(border=True):
        files = st.file_uploader(
            "PDF, JPG, or PNG",
            type=["pdf", "jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
        )
        reprocess = st.checkbox("Re-extract if this file / invoice # already exists", value=True)
        run = st.button("Extract", type="primary", disabled=not files)

    if run and files:
        for f in files:
            with st.spinner(f"Reading {f.name}…"):
                result = api(
                    "POST",
                    f"/documents?force={'true' if reprocess else 'false'}",
                    files={"file": (f.name, f.getvalue(), f.type or "application/octet-stream")},
                )
            if not result:
                continue
            if result.get("duplicate"):
                st.info(f"Already stored — skipped `{f.name}` (id {result['id']}).")
                continue
            with st.container(border=True):
                st.markdown(
                    f"**{result.get('vendor') or 'Unknown'}** · "
                    f"`{result.get('invoice_no') or 'no #'}` · "
                    f"{money(result.get('gross_amount'), result.get('currency'))} · "
                    f"`{result.get('status')}`"
                )
                if result.get("note") or result.get("review_reason"):
                    st.warning(result.get("note") or result.get("review_reason"))


def render_review(docs: list[dict]) -> None:
    page_header(
        "Review",
        "Check what the model pulled out",
        "Confirm as-is keeps the note (useful for the intentional bad-math sample).",
    )
    pending = [d for d in docs if d.get("status") in ("needs_review", "auto_ok", "failed")]
    if not pending:
        st.info("Inbox is clear. Everything is confirmed, or you have not uploaded yet.")
        return

    labels = {
        d["id"]: (
            f"#{d['id']} · {d.get('invoice_no') or 'no #'} · "
            f"{d.get('vendor') or '?'} · {d.get('status')} · "
            f"{money(d.get('gross_amount'), d.get('currency'))}"
        )
        for d in pending
    }
    pick = st.selectbox("Document", options=list(labels.keys()), format_func=lambda i: labels[i])
    doc = next(d for d in pending if d["id"] == pick)
    note_text = doc.get("note") or doc.get("review_reason") or ""

    col_img, col_form = st.columns([1.1, 1], gap="large")
    with col_img:
        with st.container(border=True):
            path = Path(doc["file_path"])
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"} and path.exists():
                st.image(str(path), use_container_width=True)
            else:
                st.info(path.name)
            if note_text:
                st.warning(f"**Note:** {note_text}")
    with col_form:
        edit_form(doc, "review_form", confirm=True)


def render_invoices(docs: list[dict]) -> None:
    page_header(
        "Invoices",
        "Everything saved",
        "Filter, edit, delete, or export CSV for the accountant.",
    )
    f1, f2, f3, f4 = st.columns(4)
    status_f = f1.selectbox("Status", ["(all)", "auto_ok", "needs_review", "confirmed", "failed"])
    cat_f = f2.selectbox("Category", ["(all)", *CATEGORIES])
    currency_f = f3.selectbox(
        "Currency",
        ["(all)", *sorted({d.get("currency") for d in docs if d.get("currency")})],
    )
    date_from = f4.text_input("From date", "")

    filtered = docs
    if status_f != "(all)":
        filtered = [d for d in filtered if d.get("status") == status_f]
    if cat_f != "(all)":
        filtered = [d for d in filtered if d.get("category") == cat_f]
    if currency_f != "(all)":
        filtered = [d for d in filtered if d.get("currency") == currency_f]
    if date_from.strip():
        filtered = [d for d in filtered if (d.get("issue_date") or "") >= date_from.strip()]

    with st.container(border=True):
        if filtered:
            totals: dict[str, float] = defaultdict(float)
            for d in filtered:
                totals[d.get("currency") or "?"] += float(d.get("gross_amount") or 0)
            st.caption(
                f"{len(filtered)} rows · "
                + " · ".join(f"{c}: {v:,.2f}" for c, v in sorted(totals.items()))
            )
            show_table(
                pd.DataFrame(filtered)[
                    [
                        "id", "invoice_no", "vendor", "issue_date", "currency",
                        "net_amount", "vat_amount", "vat_rate", "gross_amount",
                        "category", "status", "note",
                    ]
                ]
            )
        else:
            st.info("No rows match.")

    csv_text = api("GET", "/export.csv")
    if csv_text:
        st.download_button("Download CSV", data=csv_text, file_name="invoices.csv", mime="text/csv")

    st.markdown("#### Edit or delete")
    if not docs:
        return
    id_labels = {
        d["id"]: f"#{d['id']} · {d.get('invoice_no') or '—'} · {d.get('vendor') or '?'}"
        for d in docs
    }
    edit_id = st.selectbox("Pick a row", options=list(id_labels.keys()), format_func=lambda i: id_labels[i])
    doc = next(d for d in docs if d["id"] == edit_id)
    c_edit, c_del = st.columns([3, 1])
    with c_edit:
        edit_form(doc, f"edit_{edit_id}", confirm=False)
    with c_del:
        st.write("")
        st.write("")
        if st.button("Delete this invoice", type="secondary", use_container_width=True):
            st.session_state["confirm_delete_id"] = edit_id
        if st.session_state.get("confirm_delete_id") == edit_id:
            st.warning(f"Really delete #{edit_id}?")
            if st.button("Yes, delete", type="primary"):
                api("DELETE", f"/documents/{edit_id}")
                st.session_state.pop("confirm_delete_id", None)
                st.rerun()
            if st.button("Cancel"):
                st.session_state.pop("confirm_delete_id", None)
                st.rerun()


def render_analyze(docs: list[dict]) -> None:
    page_header(
        "Analyze",
        "Model briefing on your spend",
        "Same local model, but this time on the numbers — month-over-month, categories, weird notes.",
    )
    st.caption(f"{len(docs)} invoices in the database right now.")
    if st.button("Run analysis", type="primary"):
        with st.spinner("Talking to Ollama…"):
            result = api("POST", "/analyze")
        if result:
            st.session_state.analysis = result

    result = st.session_state.analysis
    if not result:
        st.info("Hit Run analysis when you have a few invoices loaded.")
        return

    with st.container(border=True):
        st.markdown(result.get("analysis") or "")
        st.caption(f"Model: `{result.get('model')}`")

    snap = result.get("snapshot") or {}
    totals = snap.get("totals") or {}
    mom = snap.get("month_over_month") or []
    cols = st.columns(2)
    with cols[0]:
        with st.container(border=True):
            st.markdown("**By category (EUR, input to the model)**")
            st.json(totals.get("by_category_eur") or totals.get("by_category") or {})
    with cols[1]:
        with st.container(border=True):
            st.markdown("**Month-over-month deltas (EUR)**")
            if mom:
                show_table(pd.DataFrame(mom))
            else:
                st.caption("Need at least two months of dated invoices.")
    fx_meta = (result.get("snapshot") or {}).get("fx") or {}
    if fx_meta.get("disclaimer"):
        st.caption(fx_meta["disclaimer"])


def render_about() -> None:
    page_header("About", "Why Invoico exists", "Hacktoberfest 2026 · Week 2 · Side Hustle")
    st.markdown(
        """
Hi — I'm **mohamedation**.

I built Invoico for the
[Hacktoberfest Open-Source AI Challenge: Week 2 — Side Hustle](https://dev.to/challenges/hacktoberfest-week2-2026-10-12).

Freelancers sit on folders of PDFs and phone photos. Cloud bookkeeping wants those
on someone else's servers. Client contracts (and my own comfort) often say no.

So the loop stays on the laptop: local vision model reads the page → Python checks
the math → you review → CSV for the accountant. Theme toggle and a wipe-database
button live under **Settings** in the sidebar (I killed the Streamlit hamburger menu
on purpose — Deploy / screencast were just noise).

The side hustle is packaged software — one-time or yearly for updates — not a SaaS. Inference stays on your machine.

If this helps you ship the quarter-end folder without uploading it anywhere, cool.
        """
    )


def render_settings() -> None:
    page_header("Settings", "App preferences", "Theme + a nuclear option for the local database.")

    with st.container(border=True):
        st.markdown("**Theme**")
        choice = st.radio(
            "Appearance",
            options=["light", "dark"],
            index=0 if st.session_state.theme == "light" else 1,
            horizontal=True,
            label_visibility="collapsed",
        )
        if choice != st.session_state.theme:
            st.session_state.theme = choice
            st.rerun()

    with st.container(border=True):
        st.markdown("**Danger zone**")
        st.write("Wipe every invoice and learned vendor→category rule from the local SQLite file.")
        if st.checkbox("I understand this cannot be undone"):
            if st.button("Clear entire database", type="primary"):
                result = api("DELETE", "/documents")
                if result is not None:
                    st.session_state.analysis = None
                    st.success(f"Deleted {result.get('deleted', 0)} invoices.")
                    st.rerun()


# --- shell ---
with st.sidebar:
    st.markdown('<p class="invoico-brand">Invoico</p>', unsafe_allow_html=True)
    st.markdown('<p class="invoico-tag">Local invoices. local AI</p>', unsafe_allow_html=True)

    for name in PAGES:
        active = st.session_state.page == name
        if st.button(
            name,
            key=f"nav_{name}",
            use_container_width=True,
            type="primary" if active else "secondary",
        ):
            st.session_state.page = name
            st.rerun()

    st.divider()
    health = api("GET", "/health")
    if health:
        if health.get("ok"):
            st.success("Ollama connected")
        else:
            st.warning("Ollama not ready")
        st.caption(f"`{health.get('model') or settings.model}`")
    st.caption("API `127.0.0.1:8000`")

page = st.session_state.page
docs = api("GET", "/documents") or []

if page == "Overview":
    render_overview(docs)
elif page == "Upload":
    render_upload()
elif page == "Review":
    render_review(docs)
elif page == "Invoices":
    render_invoices(docs)
elif page == "Analyze":
    render_analyze(docs)
elif page == "About":
    render_about()
else:
    render_settings()
