import os
import re
import base64
import streamlit as st
import streamlit.components.v1 as components


from google import genai
from google.genai import types

from dotenv import load_dotenv
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
col1, col2 = st.columns([0.6, 1])

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
            # Ensure file_selector is valid (in options) and synced
            current_selection = st.session_state.get("file_selector")
            if current_selection not in pdf_files:
                if st.session_state.current_file in pdf_files:
                    st.session_state.file_selector = st.session_state.current_file
                elif pdf_files:
                    st.session_state.file_selector = pdf_files[0]
            
            selected_file = st.selectbox("Select PDF File", pdf_files, key="file_selector")
            
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
            
            img_bytes = render_page(
                pdf_path, 
                sig=str(os.path.getsize(pdf_path)), 
                page=st.session_state.current_page, 
                dpi=500, 
            )
            st.image(img_bytes, use_container_width=True)

# --- RIGHT COLUMN: Gemini Chat ---
with col2:
    st.header("🤖 Daemini")
    
    with st.container(height=750):
        # Trigger auto-scroll for this container if flag is set
        if st.session_state.get("scroll_to_top"):
            # This JS tries to find the second scrollable container (Index 1 usually matches the right column in 2-col layout)
            # and scrolls it to top.
            js = '''
            <script>
                var candidates = window.parent.document.querySelectorAll('div[data-testid="stVerticalBlockBorderWrapper"]');
                if (candidates.length > 1) {
                    // Try to scroll the inner scrollable div of the second column container
                    var target = candidates[1].querySelector('div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlock"]');
                    if (!target) {
                         // Fallback: try finding any scrollable element within the second column wrapper
                         target = candidates[1].querySelector('[data-testid="stVerticalBlock"]');
                    }
                    if (target) {
                        target.scrollTop = 0;
                    }
                    
                    // Alternative: Select all scrollable containers and try to scroll the one intended
                    var scrollables = window.parent.document.querySelectorAll(".st-emotion-cache-12fmw14.e1f1d6gn3"); 
                    // Note: class names are unstable. Better to rely on structure if possible, but structure of StContainer is also tricky.
                    // Let's try a broader selector for the specific container height
                    var containers = window.parent.document.querySelectorAll('div[data-testid="stVerticalBlockBorderWrapper"]');
                    if(containers.length >= 2) {
                         var scroller = containers[1].querySelector('div[class*="st-emotion-cache"]'); // Common scrollable class prefix
                         if(scroller) scroller.scrollTop = 0;
                    }
                }
                
                // Simpler, more robust approach given we are INSIDE the container:
                // We can't easily reference "this" container from iframe. 
                // Best effort: Scroll all vertical block wrappers that look like our chat container.
                var wrappers = window.parent.document.querySelectorAll('div[data-testid="stVerticalBlockBorderWrapper"]');
                wrappers.forEach(w => {
                    // Check if height style matches ~750px (approx) or just scroll the second one
                   if (w.style.height.includes("750px") || w.scrollHeight > 500) {
                        // w.scrollTop = 0; // The wrapper itself might not be the scroll target
                        var inner = w.querySelector('div[data-testid="stVerticalBlock"]');
                        if(inner) inner.scrollTop = 0;
                   }
                });
                
                // Specific target for the LAST container which is likely ours (Chat)
                var all_containers = window.parent.document.querySelectorAll('[data-testid="stVerticalBlockBorderWrapper"]');
                if (all_containers.length > 0) {
                    var last_container = all_containers[all_containers.length - 1];
                    // The scrollbar is usually on the grandparent or parent of the content
                    // Streamlit `st.container(height=...)` creates a scrollable wrapper.
                    // Let's try to reset scrollTop on the element that has `overflow: auto` or `scroll`.
                    
                    // Brute force: find the container with height 750px
                    var specific_container = Array.from(all_containers).find(el => el.style.height.includes("750px"));
                    if(specific_container) {
                        specific_container.scrollTop = 0;
                        // Also try its children just in case
                        var children = specific_container.querySelectorAll("div");
                        children.forEach(c => c.scrollTop = 0);
                    }
                }

            </script>
            '''
            components.html(js, height=0, width=0)
            st.session_state.scroll_to_top = False

        # Initialize Client
        api_key = st.secrets.get("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY")
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
            generation_placeholder = None
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

                if turn_idx == 0 and st.session_state.chat_history[-1]["role"] == "user":
                    generation_placeholder = st.empty()

            if user_query:
                # Add user message to history
                st.session_state.chat_history.append({"role": "user", "content": user_query})
                st.rerun() # Rerun to show the user message immediately via the loop above

            # Check if the last message was from user, if so, generate response
            if generation_placeholder and st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
                with generation_placeholder.container():
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

                                st.session_state.scroll_to_top = True
                                st.rerun() 

                            except Exception as e:
                                st.error(f"오류가 발생했습니다: {e}")