import streamlit as st
import heapq
import json
import math
import html
from io import BytesIO
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# =========================
# Page config
# =========================
st.set_page_config(
    page_title="Compression Visualizer",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================
# Models
# =========================
@dataclass(order=True)
class HuffmanNode:
    freq: int
    order: int
    char: Optional[str] = field(compare=False, default=None)
    left: Optional["HuffmanNode"] = field(compare=False, default=None)
    right: Optional["HuffmanNode"] = field(compare=False, default=None)

# =========================
# Helpers
# =========================
def safe_text(value: str) -> str:
    return html.escape(str(value)).replace("\n", "<br>")

def render_card(title: str, value: str, subtitle: str = "") -> None:
    st.markdown(
        f"""
        <div class="glass-card">
            <div class="card-title">{safe_text(title)}</div>
            <div class="card-value">{safe_text(value)}</div>
            <div class="card-subtitle">{safe_text(subtitle)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def load_uploaded_text(uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    try:
        return uploaded_file.getvalue().decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""

def dot_escape(value: str) -> str:
    return json.dumps(value)

# =========================
# Huffman coding
# =========================
def huffman_encode_with_steps(text: str):
    if not text:
        return "", {}, None, [], Counter()

    freq = Counter(text)
    heap: List[HuffmanNode] = []
    steps: List[dict] = []
    order = 0

    for ch, f in sorted(freq.items(), key=lambda x: (x[1], x[0])):
        heapq.heappush(heap, HuffmanNode(f, order, ch))
        order += 1

    if len(heap) == 1:
        root = heap[0]
        codes = {root.char: "0"}
        encoded = "0" * len(text)
        return encoded, codes, root, steps, freq

    while len(heap) > 1:
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)

        merged = HuffmanNode(left.freq + right.freq, order, None, left, right)
        order += 1
        heapq.heappush(heap, merged)

        steps.append(
            {
                "left_label": left.char if left.char is not None else "node",
                "left_freq": left.freq,
                "right_label": right.char if right.char is not None else "node",
                "right_freq": right.freq,
                "new_freq": merged.freq,
            }
        )

    root = heap[0]
    codes: Dict[str, str] = {}

    def walk(node: Optional[HuffmanNode], prefix: str = ""):
        if node is None:
            return
        if node.char is not None:
            codes[node.char] = prefix or "0"
            return
        walk(node.left, prefix + "0")
        walk(node.right, prefix + "1")

    walk(root)
    encoded = "".join(codes[ch] for ch in text)
    return encoded, codes, root, steps, freq

def huffman_decode(encoded: str, root: Optional[HuffmanNode]) -> str:
    if not encoded or root is None:
        return ""

    if root.char is not None:
        return root.char * len(encoded)

    out = []
    node = root
    for bit in encoded:
        node = node.left if bit == "0" else node.right
        if node and node.char is not None:
            out.append(node.char)
            node = root
    return "".join(out)

def build_huffman_dot(root: Optional[HuffmanNode]) -> str:
    if root is None:
        return "digraph G { label=\"No tree\"; }"

    lines = [
        "digraph G {",
        "rankdir=TB;",
        'node [shape=circle, style="filled", fillcolor="#ffffff", color="#6b7280", fontname="Helvetica"];',
        'edge [color="#6b7280", fontname="Helvetica"];',
    ]

    counter = 0

    def visit(node: Optional[HuffmanNode]) -> str:
        nonlocal counter
        if node is None:
            return ""

        node_id = f"n{counter}"
        counter += 1

        label = f"{node.freq}" if node.char is None else f"{repr(node.char)[1:-1]}\\n{node.freq}"
        lines.append(f'{node_id} [label={dot_escape(label)}];')

        if node.left:
            left_id = visit(node.left)
            lines.append(f'{node_id} -> {left_id} [label="0"];')
        if node.right:
            right_id = visit(node.right)
            lines.append(f'{node_id} -> {right_id} [label="1"];')

        return node_id

    visit(root)
    lines.append("}")
    return "\n".join(lines)

# =========================
# Arithmetic coding
# =========================
def arithmetic_encode_with_steps(text: str):
    if not text:
        return 0.0, {}, [], 0.0, 0.0, 0.0, Counter()

    freq = Counter(text)
    total = len(text)
    probabilities = {ch: count / total for ch, count in sorted(freq.items(), key=lambda x: x[0])}

    ranges: Dict[str, Tuple[float, float]] = {}
    cumulative = 0.0
    for ch, prob in probabilities.items():
        low = cumulative
        high = cumulative + prob
        ranges[ch] = (low, high)
        cumulative = high

    low, high = 0.0, 1.0
    steps: List[dict] = []

    for ch in text:
        r_low, r_high = ranges[ch]
        width = high - low

        low_before, high_before = low, high
        low = low_before + width * r_low
        high = low_before + width * r_high

        steps.append(
            {
                "char": ch,
                "low_before": low_before,
                "high_before": high_before,
                "low_after": low,
                "high_after": high,
            }
        )

    encoded_value = (low + high) / 2
    interval_width = max(high - low, 1e-30)
    estimated_bits = -math.log2(interval_width)
    return encoded_value, ranges, steps, estimated_bits, low, high, freq

def arithmetic_decode(value: float, ranges: Dict[str, Tuple[float, float]], length: int) -> str:
    if not ranges or length <= 0:
        return ""

    result = []
    current = value

    for _ in range(length):
        for ch, (low, high) in ranges.items():
            if low <= current < high:
                result.append(ch)
                current = (current - low) / (high - low)
                break
    return "".join(result)

# =========================
# PDF report
# =========================
def generate_pdf_report(text: str, huff_result, arith_result) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=9, leading=12))
    styles.add(ParagraphStyle(name="Mono", parent=styles["BodyText"], fontName="Courier", fontSize=8, leading=10))

    story = []
    story.append(Paragraph("Compression Visualizer Report", styles["Title"]))
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Input text", styles["Heading2"]))
    story.append(Paragraph(safe_text(text or ""), styles["Small"]))
    story.append(Spacer(1, 0.12 * inch))

    if huff_result:
        story.append(Paragraph("Huffman Coding", styles["Heading2"]))
        h_rows = [
            ["Original bits", str(huff_result["original_bits"])],
            ["Encoded bits", str(huff_result["compressed_bits"])],
            ["Compression ratio", f'{huff_result["ratio"]:.4f}'],
            ["Savings", f'{huff_result["savings"]:.2f}%'],
        ]
        h_table = Table(h_rows, colWidths=[2.2 * inch, 3.0 * inch])
        h_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(h_table)
        story.append(Spacer(1, 0.12 * inch))

        code_lines = [f"{repr(ch)} : {code}" for ch, code in sorted(huff_result["codes"].items(), key=lambda item: (len(item[1]), item[0]))]
        story.append(Paragraph("Character codes", styles["Heading3"]))
        story.append(Paragraph(safe_text("<br>".join(code_lines[:20])), styles["Mono"]))
        story.append(Spacer(1, 0.15 * inch))

    if arith_result:
        story.append(Paragraph("Arithmetic Coding", styles["Heading2"]))
        a_rows = [
            ["Original bits", str(arith_result["original_bits"])],
            ["Estimated bits", f'{arith_result["estimated_bits"]:.4f}'],
            ["Compression ratio", f'{arith_result["ratio"]:.4f}'],
            ["Savings", f'{arith_result["savings"]:.2f}%'],
        ]
        a_table = Table(a_rows, colWidths=[2.2 * inch, 3.0 * inch])
        a_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(a_table)
        story.append(Spacer(1, 0.12 * inch))

        range_lines = [f"{repr(ch)} : [{low:.6f}, {high:.6f}]" for ch, (low, high) in arith_result["ranges"].items()]
        story.append(Paragraph("Symbol ranges", styles["Heading3"]))
        story.append(Paragraph(safe_text("<br>".join(range_lines[:20])), styles["Mono"]))

    story.append(Spacer(1, 0.18 * inch))
    story.append(Paragraph("Time complexity", styles["Heading2"]))
    story.append(Paragraph(
        safe_text(
            "Huffman coding: tree construction O(k log k), encoding O(n), decoding O(n).<br>"
            "Arithmetic coding: encoding O(n), decoding O(n), with floating-point interval updates."
        ),
        styles["Small"],
    ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

# =========================
# Theme and CSS
# =========================
dark_mode = st.sidebar.toggle("Dark mode", value=True)
accent = "#7c5cff" if dark_mode else "#5b5bd6"
bg = "#0b1020" if dark_mode else "#f4f7fb"
panel = "#121a2f" if dark_mode else "#ffffff"
panel_2 = "#17213a" if dark_mode else "#eef3ff"
text = "#eef2ff" if dark_mode else "#111827"
muted = "#a6b0cf" if dark_mode else "#5b6478"
border = "rgba(255,255,255,0.08)" if dark_mode else "rgba(17,24,39,0.08)"

st.markdown(
    f"""
    <style>
    :root {{
        --bg: {bg};
        --panel: {panel};
        --panel2: {panel_2};
        --text: {text};
        --muted: {muted};
        --accent: {accent};
        --border: {border};
    }}

    .stApp {{
        background:
            radial-gradient(circle at top left, rgba(124,92,255,0.16), transparent 28%),
            radial-gradient(circle at bottom right, rgba(0,209,178,0.10), transparent 24%),
            var(--bg);
        color: var(--text);
    }}

    .block-container {{
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 1280px;
    }}

    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, rgba(124,92,255,0.10), rgba(0,0,0,0));
        border-right: 1px solid var(--border);
    }}

    .hero {{
        background: linear-gradient(135deg, rgba(124,92,255,0.14), rgba(0,209,178,0.08));
        border: 1px solid var(--border);
        border-radius: 28px;
        padding: 26px 28px;
        box-shadow: 0 14px 44px rgba(0,0,0,0.12);
        margin-bottom: 18px;
    }}

    .hero h1 {{
        margin: 0;
        font-size: 2.05rem;
        letter-spacing: -0.04em;
        color: var(--text);
    }}

    .hero p {{
        margin: 0.35rem 0 0;
        color: var(--muted);
        font-size: 1rem;
    }}

    .glass-card {{
        background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01));
        border: 1px solid var(--border);
        border-radius: 22px;
        padding: 18px 18px 16px;
        box-shadow: 0 12px 28px rgba(0,0,0,0.12);
        margin-bottom: 12px;
    }}

    .card-title {{
        color: var(--muted);
        font-size: 0.86rem;
        text-transform: uppercase;
        letter-spacing: 0.11em;
        margin-bottom: 8px;
    }}

    .card-value {{
        color: var(--text);
        font-size: 1.5rem;
        font-weight: 700;
        line-height: 1.1;
        word-break: break-word;
    }}

    .card-subtitle {{
        color: var(--muted);
        font-size: 0.92rem;
        margin-top: 8px;
    }}

    .step-card {{
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 20px;
        padding: 16px 16px 14px;
        margin-bottom: 10px;
        transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
    }}

    .step-card.active {{
        border-color: var(--accent);
        box-shadow: 0 0 0 1px rgba(124,92,255,0.12), 0 16px 34px rgba(124,92,255,0.14);
        transform: translateY(-1px) scale(1.01);
        animation: pulse 1.4s ease-in-out infinite;
    }}

    @keyframes pulse {{
        0% {{ box-shadow: 0 0 0 0 rgba(124,92,255,0.16); }}
        70% {{ box-shadow: 0 0 0 12px rgba(124,92,255,0.00); }}
        100% {{ box-shadow: 0 0 0 0 rgba(124,92,255,0.00); }}
    }}

    .step-badge {{
        display: inline-block;
        background: rgba(124,92,255,0.12);
        color: var(--text);
        border: 1px solid rgba(124,92,255,0.24);
        border-radius: 999px;
        padding: 4px 10px;
        font-size: 0.8rem;
        margin-bottom: 10px;
    }}

    .step-body {{
        color: var(--text);
        font-size: 1.02rem;
        font-weight: 600;
        margin-bottom: 6px;
        white-space: normal;
    }}

    .step-footer {{
        color: var(--muted);
        font-size: 0.92rem;
    }}

    .section-title {{
        font-size: 1.05rem;
        font-weight: 700;
        color: var(--text);
        margin: 14px 0 8px;
    }}

    .small-muted {{
        color: var(--muted);
        font-size: 0.92rem;
    }}

    .stButton > button {{
        border-radius: 14px;
        padding: 0.65rem 1rem;
        border: 1px solid var(--border);
        background: linear-gradient(135deg, rgba(124,92,255,0.92), rgba(103,80,255,0.86));
        color: white;
        font-weight: 700;
        transition: transform 140ms ease, box-shadow 140ms ease;
        box-shadow: 0 12px 24px rgba(124,92,255,0.22);
    }}

    .stButton > button:hover {{
        transform: translateY(-1px);
        box-shadow: 0 16px 28px rgba(124,92,255,0.28);
    }}

    .stDownloadButton > button {{
        border-radius: 14px;
        padding: 0.65rem 1rem;
        border: 1px solid var(--border);
        font-weight: 700;
    }}

    textarea, input {{
        border-radius: 16px !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# Session state
# =========================
if "source_text" not in st.session_state:
    st.session_state.source_text = "hello world"

if "sample_choice" not in st.session_state:
    st.session_state.sample_choice = "Custom"

if "huff_result" not in st.session_state:
    st.session_state.huff_result = None

if "arith_result" not in st.session_state:
    st.session_state.arith_result = None

# =========================
# Sidebar
# =========================
st.sidebar.markdown("## Controls")

sample_options = [
    "Custom",
    "hello world",
    "banana bandana",
    "compression",
    "mississippi",
    "abracadabra",
]
sample_choice = st.sidebar.selectbox("Load a sample", sample_options, index=0)

uploaded = st.sidebar.file_uploader("Upload a .txt file", type=["txt"])
if uploaded is not None:
    uploaded_text = load_uploaded_text(uploaded)
    if uploaded_text:
        st.session_state.source_text = uploaded_text
        st.sidebar.success(f"Loaded {uploaded.name}")

if sample_choice != "Custom" and sample_choice != st.session_state.sample_choice:
    st.session_state.source_text = sample_choice
    st.session_state.sample_choice = sample_choice
elif sample_choice == "Custom":
    st.session_state.sample_choice = "Custom"

st.sidebar.markdown("---")
st.sidebar.caption("Encode input and use the result for decoding, comparison, or download.")

# =========================
# Header
# =========================
st.markdown(
    """
    <div class="hero">
        <h1>Compression Visualizer</h1>
        <p>Interactive visualization of Huffman coding and Arithmetic coding with encoding, decoding, and process steps.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

left, right = st.columns([1.25, 0.9])

with left:
    st.markdown("### Source text")
    st.text_area(
        "Source text",
        height=160,
        key="source_text",
        help="Type or paste text here. You can also upload a .txt file from the sidebar.",
        label_visibility="collapsed",
    )
    source_text = st.session_state.source_text.strip()

with right:
    st.markdown("### Quick stats")
    render_card("Characters", f"{len(source_text) if source_text else 0}", "Total input length")
    render_card("Unique symbols", f"{len(set(source_text)) if source_text else 0}", "Character variety")
    render_card("Raw size", f"{len(source_text) * 8 if source_text else 0} bits", "Assuming 8-bit characters")

# =========================
# Tabs
# =========================
tab_h, tab_a, tab_compare, tab_report = st.tabs(
    ["Huffman Coding", "Arithmetic Coding", "Comparison", "Report"]
)

# =========================
# Huffman tab
# =========================
with tab_h:
    st.markdown('<div class="section-title">Huffman coding explorer</div>', unsafe_allow_html=True)
    st.markdown('<div class="small-muted">Encode, decode, inspect tree merges, and download the result.</div>', unsafe_allow_html=True)

    if st.button("Encode Huffman", key="encode_huff"):
        if not source_text:
            st.warning("Please enter some text first.")
        else:
            encoded, codes, root, steps, freq = huffman_encode_with_steps(source_text)
            original_bits = len(source_text) * 8
            compressed_bits = len(encoded)
            ratio = (compressed_bits / original_bits) if original_bits else 0.0
            savings = (1 - ratio) * 100 if original_bits else 0.0

            st.session_state.huff_result = {
                "text": source_text,
                "encoded": encoded,
                "codes": codes,
                "root": root,
                "steps": steps,
                "freq": freq,
                "original_bits": original_bits,
                "compressed_bits": compressed_bits,
                "ratio": ratio,
                "savings": savings,
                "decoded": huffman_decode(encoded, root),
            }

    if st.session_state.huff_result:
        res = st.session_state.huff_result

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_card("Raw bits", f"{res['original_bits']}", "8 bits per character")
        with c2:
            render_card("Encoded bits", f"{res['compressed_bits']}", "Bitstring length")
        with c3:
            render_card("Compression ratio", f"{res['ratio']:.3f}", "Lower is better")
        with c4:
            render_card("Savings", f"{res['savings']:.1f}%", "Estimated reduction")

        col_left, col_right = st.columns([1.0, 1.0], gap="large")

        with col_left:
            st.markdown("#### Character codes")
            code_rows = [
                {"Character": repr(ch), "Code": code, "Frequency": res["freq"][ch]}
                for ch, code in sorted(res["codes"].items(), key=lambda item: (len(item[1]), item[0]))
            ]
            st.dataframe(code_rows, use_container_width=True, hide_index=True)

            st.markdown("#### Encoded output")
            st.code(res["encoded"], language="text")

            st.download_button(
                "Download encoded bitstring",
                data=res["encoded"],
                file_name="huffman_encoded.txt",
                mime="text/plain",
                key="huff_dl_bits",
            )

            payload = {
                "text": res["text"],
                "encoded": res["encoded"],
                "codes": res["codes"],
                "frequency": dict(res["freq"]),
            }
            st.download_button(
                "Download Huffman payload",
                data=json.dumps(payload, indent=2),
                file_name="huffman_payload.json",
                mime="application/json",
                key="huff_dl_json",
            )

        with col_right:
            st.markdown("#### Decode")
            if st.button("Decode Huffman output", key="decode_huff"):
                decoded = huffman_decode(res["encoded"], res["root"])
                st.success(f"Decoded text: {decoded}")

            st.markdown("#### Huffman tree")
            st.graphviz_chart(build_huffman_dot(res["root"]))

            st.markdown("#### Tree merge playback")
            if res["steps"]:
                active_idx = st.slider(
                    "Highlight merge step",
                    0,
                    len(res["steps"]) - 1,
                    len(res["steps"]) - 1,
                    key="huff_step_slider",
                )
                for idx, step in enumerate(res["steps"]):
                    active = idx == active_idx
                    klass = "step-card active" if active else "step-card"
                    st.markdown(
                        f"""
                        <div class="{klass}">
                            <div class="step-badge">Merge {idx + 1}</div>
                            <div class="step-body">
                                {safe_text(step['left_label'])} ({step['left_freq']}) +
                                {safe_text(step['right_label'])} ({step['right_freq']})
                            </div>
                            <div class="step-footer">
                                New node frequency: {step['new_freq']}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.info("This input has only one unique symbol, so there are no merges to animate.")

            with st.expander("Show frequency table"):
                st.dataframe(
                    [{"Character": repr(ch), "Frequency": f} for ch, f in sorted(res["freq"].items())],
                    use_container_width=True,
                    hide_index=True,
                )

# =========================
# Arithmetic tab
# =========================
with tab_a:
    st.markdown('<div class="section-title">Arithmetic coding explorer</div>', unsafe_allow_html=True)
    st.markdown('<div class="small-muted">Observe interval updates, inspect ranges, and download the result.</div>', unsafe_allow_html=True)

    if st.button("Encode Arithmetic", key="encode_arith"):
        if not source_text:
            st.warning("Please enter some text first.")
        else:
            value, ranges, steps, estimated_bits, low, high, freq = arithmetic_encode_with_steps(source_text)
            original_bits = len(source_text) * 8
            ratio = (estimated_bits / original_bits) if original_bits else 0.0
            savings = (1 - ratio) * 100 if original_bits else 0.0

            st.session_state.arith_result = {
                "text": source_text,
                "value": value,
                "ranges": ranges,
                "steps": steps,
                "estimated_bits": estimated_bits,
                "interval_low": low,
                "interval_high": high,
                "freq": freq,
                "original_bits": original_bits,
                "ratio": ratio,
                "savings": savings,
                "decoded": arithmetic_decode(value, ranges, len(source_text)),
            }

    if st.session_state.arith_result:
        res = st.session_state.arith_result

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_card("Raw bits", f"{res['original_bits']}", "8 bits per character")
        with c2:
            render_card("Estimated bits", f"{res['estimated_bits']:.2f}", "From final interval")
        with c3:
            render_card("Compression ratio", f"{res['ratio']:.3f}", "Estimated")
        with c4:
            render_card("Savings", f"{res['savings']:.1f}%", "Estimated reduction")

        col_left, col_right = st.columns([1.0, 1.0], gap="large")

        with col_left:
            st.markdown("#### Symbol ranges")
            range_rows = [
                {"Character": repr(ch), "Low": f"{low:.6f}", "High": f"{high:.6f}"}
                for ch, (low, high) in res["ranges"].items()
            ]
            st.dataframe(range_rows, use_container_width=True, hide_index=True)

            st.markdown("#### Encoded value")
            st.code(f"{res['value']:.20f}", language="text")

            st.download_button(
                "Download arithmetic payload",
                data=json.dumps(
                    {
                        "text": res["text"],
                        "value": res["value"],
                        "ranges": res["ranges"],
                        "frequency": dict(res["freq"]),
                    },
                    indent=2,
                ),
                file_name="arithmetic_payload.json",
                mime="application/json",
                key="arith_dl_json",
            )

        with col_right:
            st.markdown("#### Decode")
            if st.button("Decode Arithmetic output", key="decode_arith"):
                decoded = arithmetic_decode(res["value"], res["ranges"], len(res["text"]))
                st.success(f"Decoded text: {decoded}")

            st.markdown("#### Interval playback")
            if res["steps"]:
                active_idx = st.slider(
                    "Highlight interval step",
                    0,
                    len(res["steps"]) - 1,
                    len(res["steps"]) - 1,
                    key="arith_step_slider",
                )
                for idx, step in enumerate(res["steps"]):
                    active = idx == active_idx
                    klass = "step-card active" if active else "step-card"
                    st.markdown(
                        f"""
                        <div class="{klass}">
                            <div class="step-badge">Step {idx + 1}</div>
                            <div class="step-body">
                                {safe_text(step['char'])} → [{step['low_before']:.5f}, {step['high_before']:.5f}]
                            </div>
                            <div class="step-footer">
                                Updated to [{step['low_after']:.5f}, {step['high_after']:.5f}]
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.info("No interval steps available for this input.")

            with st.expander("Show symbol frequencies"):
                st.dataframe(
                    [{"Character": repr(ch), "Frequency": f} for ch, f in sorted(res["freq"].items())],
                    use_container_width=True,
                    hide_index=True,
                )

# =========================
# Comparison tab
# =========================
with tab_compare:
    st.markdown('<div class="section-title">Side-by-side comparison</div>', unsafe_allow_html=True)
    st.markdown('<div class="small-muted">Run both algorithms on the current input to compare output and compression.</div>', unsafe_allow_html=True)

    if st.button("Run comparison on current input", key="run_compare"):
        if not source_text:
            st.warning("Please enter some text first.")
        else:
            h_encoded, h_codes, h_root, h_steps, h_freq = huffman_encode_with_steps(source_text)
            h_original_bits = len(source_text) * 8
            h_compressed_bits = len(h_encoded)
            h_ratio = (h_compressed_bits / h_original_bits) if h_original_bits else 0.0
            h_savings = (1 - h_ratio) * 100 if h_original_bits else 0.0

            a_value, a_ranges, a_steps, a_estimated_bits, a_low, a_high, a_freq = arithmetic_encode_with_steps(source_text)
            a_ratio = (a_estimated_bits / h_original_bits) if h_original_bits else 0.0
            a_savings = (1 - a_ratio) * 100 if h_original_bits else 0.0

            st.session_state.huff_result = {
                "text": source_text,
                "encoded": h_encoded,
                "codes": h_codes,
                "root": h_root,
                "steps": h_steps,
                "freq": h_freq,
                "original_bits": h_original_bits,
                "compressed_bits": h_compressed_bits,
                "ratio": h_ratio,
                "savings": h_savings,
                "decoded": huffman_decode(h_encoded, h_root),
            }

            st.session_state.arith_result = {
                "text": source_text,
                "value": a_value,
                "ranges": a_ranges,
                "steps": a_steps,
                "estimated_bits": a_estimated_bits,
                "interval_low": a_low,
                "interval_high": a_high,
                "freq": a_freq,
                "original_bits": h_original_bits,
                "ratio": a_ratio,
                "savings": a_savings,
                "decoded": arithmetic_decode(a_value, a_ranges, len(source_text)),
            }

    if st.session_state.huff_result and st.session_state.arith_result:
        h = st.session_state.huff_result
        a = st.session_state.arith_result

        if h["text"] != a["text"]:
            st.warning("The stored Huffman and Arithmetic results were generated from different inputs. Run comparison on the current input to compare fairly.")
        else:
            left_col, right_col = st.columns(2, gap="large")

            with left_col:
                st.markdown("#### Huffman")
                render_card("Encoded bits", f"{h['compressed_bits']}", "Exact bitstring length")
                render_card("Compression ratio", f"{h['ratio']:.3f}", "Lower is better")
                render_card("Savings", f"{h['savings']:.1f}%", "Estimated reduction")
                st.code(h["encoded"], language="text")

            with right_col:
                st.markdown("#### Arithmetic")
                render_card("Estimated bits", f"{a['estimated_bits']:.2f}", "From final interval")
                render_card("Compression ratio", f"{a['ratio']:.3f}", "Estimated")
                render_card("Savings", f"{a['savings']:.1f}%", "Estimated reduction")
                st.code(f"{a['value']:.20f}", language="text")

            st.markdown("#### Compression ratio graph")
            fig, ax = plt.subplots(figsize=(7, 4))
            labels = ["Huffman", "Arithmetic"]
            values = [h["ratio"], a["ratio"]]
            ax.bar(labels, values)
            ax.set_ylabel("Compression ratio")
            ax.set_ylim(0, max(values + [1.0]) * 1.25)
            ax.set_title("Comparison of compression ratio")
            st.pyplot(fig, clear_figure=True)

            st.markdown("#### Time complexity")
            time_rows = [
                ["Huffman coding", "O(k log k) for tree build, O(n) for encoding and decoding"],
                ["Arithmetic coding", "O(n) for encoding and decoding"],
            ]
            st.table(time_rows)

            st.markdown("#### Comparison view")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("Huffman Coding")
                st.markdown(
                    f"""
                    <div class="glass-card">
                        <div class="card-title">Summary</div>
                        <div class="card-value">{h['compressed_bits']} bits</div>
                        <div class="card-subtitle">Ratio: {h['ratio']:.3f} | Savings: {h['savings']:.1f}%</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.write("Decoded text:", h["decoded"])

            with c2:
                st.markdown("Arithmetic Coding")
                st.markdown(
                    f"""
                    <div class="glass-card">
                        <div class="card-title">Summary</div>
                        <div class="card-value">{a['estimated_bits']:.2f} bits</div>
                        <div class="card-subtitle">Ratio: {a['ratio']:.3f} | Savings: {a['savings']:.1f}%</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.write("Decoded text:", a["decoded"])
    else:
        st.info("Run comparison to generate both results from the current text.")

# =========================
# Report tab
# =========================
with tab_report:
    st.markdown('<div class="section-title">Report export</div>', unsafe_allow_html=True)
    st.markdown('<div class="small-muted">Generate a PDF-style summary of the current input and results.</div>', unsafe_allow_html=True)

    if st.session_state.huff_result or st.session_state.arith_result:
        pdf_bytes = generate_pdf_report(source_text, st.session_state.huff_result, st.session_state.arith_result)
        st.download_button(
            "Download PDF report",
            data=pdf_bytes,
            file_name="compression_report.pdf",
            mime="application/pdf",
            key="download_pdf_report",
        )

        st.markdown("#### Report summary")
        if st.session_state.huff_result:
            h = st.session_state.huff_result
            st.write(f"Huffman ratio: {h['ratio']:.3f}")
            st.write(f"Huffman savings: {h['savings']:.1f}%")
        if st.session_state.arith_result:
            a = st.session_state.arith_result
            st.write(f"Arithmetic ratio: {a['ratio']:.3f}")
            st.write(f"Arithmetic savings: {a['savings']:.1f}%")

        st.markdown("#### Time complexity")
        st.table(
            [
                ["Huffman coding", "O(k log k) tree build, O(n) encode/decode"],
                ["Arithmetic coding", "O(n) encode/decode"],
            ]
        )
    else:
        st.info("Encode at least one algorithm before exporting a report.")

# =========================
# Footer
# =========================
st.markdown("---")
st.markdown(
    "<div class='small-muted'>Encoding, decoding, process visualization, comparison, and report export.</div>",
    unsafe_allow_html=True,
)