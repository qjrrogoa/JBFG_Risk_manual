
import fitz
import streamlit as st
from typing import Tuple



# =====================================================
# PDF 페이지 수 / 렌더 (하이라이트 포함)
# =====================================================
@st.cache_data(show_spinner=False)
def get_total_pages(pdf_path: str, sig: str) -> int:
    doc = fitz.open(pdf_path)
    try:
        return doc.page_count
    finally:
        doc.close()


@st.cache_data(show_spinner=False)
def render_page(
    pdf_path: str,
    sig: str,
    page: int,
    dpi: int,
) -> bytes:
    doc = fitz.open(pdf_path)
    try:
        total = doc.page_count
        page = max(1, min(int(page), total))
        p = doc.load_page(page - 1)

        pix = p.get_pixmap(dpi=int(dpi), annots=False)
        return pix.tobytes("png")
    finally:
        doc.close()