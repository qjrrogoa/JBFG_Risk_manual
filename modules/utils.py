
import re
import streamlit as st
import streamlit.components.v1 as components

from pathlib import Path
from typing import List, Dict

# =====================================================
# 키워드 정제/추출
# =====================================================
_STOPWORDS = {
    "뭐야", "무엇", "뭔가", "왜", "어떻게", "언제", "어디", "누구",
    "알려줘", "알려줘요", "알려주세요", "알려주라",
    "설명", "설명해", "설명해줘", "설명해봐", "설명좀", "설명좀해줘",
    "정의", "의미",
    "가능", "가능해", "가능할까", "될까", "되나", "되나요",
    "해주세요", "해주세요요", "해줘", "해줘요", "해주라",
    "있어", "없어", "인가", "인가요", "나요", "요",
    "좀", "그리고", "혹시", "일단", "그냥", "같은",
    "정도", "쯤", "정도로", "정도만", "정도면",
    "관련", "대해서", "대해", "관해",
    "찾아", "찾아줘", "찾아줘요", "찾아주세요", "찾아주라", "찾아봐", "찾아봐줘", "찾아보기", "찾기",
    "보여", "보여줘", "보여줘요", "보여주세요", "보여주라", "보여봐",
    "정리", "정리해", "정리해줘", "정리해주세요",
    "요약", "요약해", "요약해줘", "요약해주세요",
    "추출", "추출해", "추출해줘", "추출해주세요",
    "확인", "확인해", "확인해줘", "확인해주세요",
    "검토", "검토해", "검토해줘", "검토해주세요",
    "내용", "내용들", "관련내용",
    "부분", "부분만", "항목", "항목들",
    "구간", "대목", "문장", "표", "그림", "페이지",
    "이거", "그거", "저거", "이것", "그것", "저것",
    "여기", "거기", "저기",
    "이부분", "그부분", "저부분",
    "대한민국", "한국", "정부", "중앙정부", "은행", "한국은행",
    # Common functional words
    "하는", "한", "할", "하여", "해", "해야", "하면", "하기",
    "있는", "있다", "있으며", "있고",
    "없는", "없다", "없으며", "없고",
    "되는", "된", "될", "되어", "되면", "되기",
    "대한", "위해", "통해", "따라", "의해",
    "경우", "때문", "기준", "사항", "방법", "절차", "방식",
    "포함", "제외", "해당", "이상", "이하", "미만", "초과",
}

_PARTICLE_RE = re.compile(
    r"(에서|으로|로|에게|께|부터|까지|보다|처럼|만|도|의|은|는|이|가|을|를|와|과|랑|하고|에|서|께서|로서|로써)$"
)


def normalize_token(tok: str) -> str:
    tok = tok.strip()
    tok = re.sub(r"[^\uAC00-\uD7A3A-Za-z0-9]+", "", tok)
    if not tok:
        return ""
    tok = _PARTICLE_RE.sub("", tok)
    return tok


def extract_query_keywords(query: str) -> List[str]:
    q = (query or "").strip()
    if not q:
        return []
    raw = re.split(r"\s+", q)
    tokens = []
    for t in raw:
        nt = normalize_token(t)
        if not nt:
            continue
        if nt in _STOPWORDS:
            continue
        if len(nt) < 2:
            continue
        tokens.append(nt)
    out = []
    for t in tokens:
        if t not in out:
            out.append(t)
    return out


def make_highlight_terms(query: str, chunk_text: str, max_terms: int = 8) -> List[str]:
    # ✅ 핵심 키워드 3개만 추출 (너무 많은 하이라이트 방지)
    keywords = extract_query_keywords(query)[:3]
    
    # phrase = re.sub(r"\s+", " ", (chunk_text or "")).strip()[:30]
    terms = keywords[:]
    
    # ✅ "Chunk 문구 자체"를 하이라이트하면 너무 지저분해 보여서 제거함.
    # if phrase and phrase not in terms:
    #     terms.append(phrase)
        
    out = []
    for t in terms:
        if t and t not in out:
            out.append(t)
        if len(out) >= max_terms:
            break
    return out



# =====================================================
# 캐시 키
# =====================================================
def file_signature(p: Path) -> str:
    s = p.stat()
    return f"{p.resolve()}|{s.st_size}|{s.st_mtime_ns}"


def all_pdfs_signature(pdf_files: Dict[str, Path]) -> str:
    return "||".join(file_signature(p) for p in pdf_files.values())


# =====================================================
# 스크롤 유틸 (best-effort)
# =====================================================
def request_scroll_top():
    st.session_state.scroll_to_top = True


def apply_scroll_top_if_needed():
    if st.session_state.get("scroll_to_top"):
        components.html(
            """
            <script>
              try { window.parent.scrollTo(0,0); } catch(e) {}
              try { window.scrollTo(0,0); } catch(e) {}
            </script>
            """,
            height=0,
            width=0,
        )
        st.session_state.scroll_to_top = False
