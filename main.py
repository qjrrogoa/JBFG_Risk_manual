import os
import re
import base64
import streamlit as st


from google import genai
from google.genai import types

from dotenv import load_dotenv
from modules.utils import extract_query_keywords
from modules.pdf_processor import render_page, get_total_pages

# 1. Load environment variables
load_dotenv('../../etc/.env') # Adjust path if necessary, user provided '../../etc/.env'

# 2. Configure Streamlit
st.set_page_config(layout="wide", page_title="RAG v2 - Gemini File Search")

# 3. Initialize Session State
if "current_page" not in st.session_state:
    st.session_state.current_page = 1
if "current_file" not in st.session_state:
    st.session_state.current_file = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "pending_auto_jump" not in st.session_state:
    st.session_state.pending_auto_jump = None
if "scroll_to_top" not in st.session_state:
    st.session_state.scroll_to_top = False

# Check for pending auto-jump (must be done before widgets are rendered)
if st.session_state.pending_auto_jump:
    target = st.session_state.pending_auto_jump
    st.session_state.current_file = target['file']
    st.session_state.file_selector = target['file']
    st.session_state.current_page = target['page']
    st.session_state.page_input = str(target['page'])
    st.session_state.pending_auto_jump = None # Clear after applying

# 4. Helper Functions
def get_pdf_files(data_dir="data"):
    """Scans the data directory for PDF files."""
    pdf_files = []
    if os.path.exists(data_dir):
        for f in os.listdir(data_dir):
            if f.lower().endswith(".pdf"):
                pdf_files.append(f)
    return sorted(pdf_files)

def set_page(page):
    st.session_state.current_page = int(page)
    st.session_state.page_input = str(page)

def on_page_change():
    """Callback for page number input change."""
    try:
        new_page = int(st.session_state.page_input)
        # Validation will happen in the main body where total_pages is available
        # or we can check simple bounds here if possible.
        # Ideally, we just set it and let the main loop clamp it.
        st.session_state.current_page = new_page
    except ValueError:
        pass # Ignore invalid input

def normalize_source_name(source_name: str, available_files: list) -> str:
    """
    Matches the source name from Gemini to the actual file in the data directory.
    Tries exact match, then adding .pdf.
    """
    if source_name in available_files:
        return source_name
    
    # Try adding .pdf
    candidate = f"{source_name}.pdf"
    if candidate in available_files:
        return candidate
        
    return source_name

def jump_to_source(title: str, page: int, available_files: list):
    """Callback to jump to a specific source and page."""
    real_source = normalize_source_name(title, available_files)
    if real_source in available_files:
        st.session_state.current_file = real_source
        st.session_state.file_selector = real_source
        st.session_state.current_page = page
        st.session_state.page_input = str(page)
    else:
        st.toast(f"Cannot find file: {title}")

# 5. Layout
col1, col2 = st.columns([1, 1])

# --- LEFT COLUMN: PDF Viewer ---
with col1:
    st.header("📄 PDF")
    
    with st.container(height=1500):
        # File Selection
        pdf_files = get_pdf_files()
        if not pdf_files:
            st.error("No PDF files found in 'data/' directory.")
            selected_file = None
        else:
            # Default to first file or previously selected
            idx = 0
            if st.session_state.current_file in pdf_files:
                idx = pdf_files.index(st.session_state.current_file)
            
            selected_file = st.selectbox("Select PDF File", pdf_files, index=idx, key="file_selector")
            
            # Update session state if changed via selectbox
            if selected_file != st.session_state.current_file:
                 st.session_state.current_file = selected_file
                 st.session_state.current_page = 1 # Reset to page 1 on file change

        if selected_file:
            pdf_path = os.path.join("data", selected_file)
            
            # Page Navigation
            total_pages = get_total_pages(pdf_path, sig=str(os.path.getsize(pdf_path)))
            
            # Validation for page number
            if st.session_state.current_page < 1:
                st.session_state.current_page = 1
            if st.session_state.current_page > total_pages:
                st.session_state.current_page = total_pages

            c1, c2, c3 = st.columns([1, 2, 1], vertical_alignment="center")
            with c1:
                if st.button("◀ Prev", use_container_width=True):
                    if st.session_state.current_page > 1:
                        st.session_state.current_page -= 1
                        st.rerun()
            with c2:
                # Page Input Field
                st.text_input(
                    "Page", 
                    value=str(st.session_state.current_page),
                    key="page_input",
                    on_change=on_page_change,
                    label_visibility="collapsed"
                )
                st.caption(f" / {total_pages}")

            with c3:
                if st.button("Next ▶", use_container_width=True):
                    if st.session_state.current_page < total_pages:
                        st.session_state.current_page += 1
                        st.rerun()

            # Render PDF
            # We can extract keywords from the last query for highlighting if needed
            highlight_terms = []
            if st.session_state.chat_history:
                 last_query = st.session_state.chat_history[-1]["role"] == "user" and st.session_state.chat_history[-1]["content"] or ""
                 # Actually, history order might be User, AI, User, AI. We want the last USER query.
                 # Simple approach: grab terms from the input widget if possible, or just pass empty for now.
                 # Let's try to grab from last user message in history.
                 for msg in reversed(st.session_state.chat_history):
                     if msg["role"] == "user":
                         highlight_terms = extract_query_keywords(msg["content"])
                         break
            
            img_bytes = render_page(
                pdf_path, 
                sig=str(os.path.getsize(pdf_path)), 
                page=st.session_state.current_page, 
                dpi=150, 
                highlight_terms=tuple(highlight_terms)
            )
            st.image(img_bytes, use_container_width=True)

# --- RIGHT COLUMN: Gemini Chat ---
with col2:
    st.header("🤖 Daemini")
    
    with st.container(height=2000):
        # Initialize Client
        api_key = st.secrets["OPENAI_API_KEY"]
        if not api_key:
            st.error("GOOGLE_API_KEY not found in environment variables.")
        else:
            client = genai.Client(api_key=api_key)
            
            # Chat Interface
            user_query = st.chat_input("질문을 입력하세요...")
            
            # Group messages into conversation turns (User -> Assistant)
            turns = []
            current_turn = []
            for msg in st.session_state.chat_history:
                if msg["role"] == "user":
                    if current_turn:
                        turns.append(current_turn)
                    current_turn = [msg]
                else:
                    current_turn.append(msg)
            if current_turn:
                turns.append(current_turn)

            # Display turns in reverse order (Newest turn at the top)
            for turn_idx, turn in enumerate(reversed(turns)):
                st.divider() # Visual separation between turns
                
                # Within a turn, display messages in chronological order (Question -> Answer)
                for msg_idx, msg in enumerate(turn):
                    with st.chat_message(msg["role"]):
                        st.write(msg["content"])
                        
                        # If message has sources, display them (only for assistant usually)
                        if "sources" in msg and msg["sources"]:
                            st.write("📌 **관련 출처:**")
                            
                            # Deduplicate sources locally for display
                            unique_sources = []
                            seen = set()
                            for s in msg["sources"]:
                                key = (s['title'], s['page'])
                                if key not in seen:
                                    seen.add(key)
                                    unique_sources.append(s)
                                    
                            # Display buttons
                            for idx, src in enumerate(unique_sources):
                                label = f"📄 {src['title']} (p.{src['page']})"
                                # Unique key is crucial (mix turn_idx to avoid collision)
                                btn_key = f"hist_src_{turn_idx}_{msg_idx}_{idx}"
                                st.button(
                                    label, 
                                    key=btn_key,
                                    on_click=jump_to_source,
                                    args=(src['title'], src['page'], pdf_files)
                                )

            if user_query:
                # Add user message to history
                st.session_state.chat_history.append({"role": "user", "content": user_query})
                st.rerun() # Rerun to show the user message immediately via the loop above

            # Check if the last message was from user, if so, generate response
            if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
                with st.chat_message("assistant"):
                    with st.spinner("문서를 검색 중입니다..."):
                        try:
                            # Call Gemini API
                            response = client.models.generate_content(
                                model="gemini-2.5-flash", 
                                contents=st.session_state.chat_history[-1]["content"],
                                config=types.GenerateContentConfig(
                                    temperature=0.0,
                                    system_instruction="""
                                    너는 금융 규제 전문가야. 
                                    반드시 제공된 'File Search' 결과 내의 정보만을 바탕으로 답변해야 해.
                                    파일에 없는 수치나 내용은 절대 지어내지 말고, 
                                    만약 파일에서 찾을 수 없다면 '해당 정보는 문서에 포함되어 있지 않습니다'라고 대답해.
                                    """,
                                    tools=[
                                        types.Tool(
                                            file_search=types.FileSearch(
                                                file_search_store_names=["fileSearchStores/jbriskmanual-01q1nf25k1tw"]
                                            )
                                        )
                                    ]
                                )
                            )
                            
                            # Process Sources
                            source_list = []
                            if response.candidates and response.candidates[0].grounding_metadata:
                                 metadata = response.candidates[0].grounding_metadata
                                 if metadata.grounding_chunks:
                                    for chunk in metadata.grounding_chunks:
                                        source = chunk.retrieved_context
                                        if source and source.text:
                                            title = source.title
                                            page_match = re.search(r'--- PAGE (\d+) ---', source.text)
                                            if page_match:
                                                page_num = int(page_match.group(1))
                                                source_list.append({"title": title, "page": page_num})
                            
                            # Display Text
                            st.markdown(response.text)
                            
                            # Save to history
                            st.session_state.chat_history.append({
                                "role": "assistant", 
                                "content": response.text,
                                "sources": source_list
                            })
                            
                            # Auto-jump to the first source if available
                            if source_list:
                                first_src = source_list[0]
                                real_source = normalize_source_name(first_src['title'], pdf_files)
                                if real_source in pdf_files:
                                    # Set pending jump for next run to avoid StreamlitAPIException
                                    st.session_state.pending_auto_jump = {
                                        'file': real_source,
                                        'page': first_src['page']
                                    }

                            st.rerun() 

                        except Exception as e:
                            st.error(f"오류가 발생했습니다: {e}")