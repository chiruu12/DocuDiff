import streamlit as st
import time
import os
from dotenv import load_dotenv
from groq import Groq
from typing import Optional, Any
from utils import BaseComparator
try:
    from utils import extract_text_from_file
    utils_available = True
except ImportError:
    utils_available = False
    st.error("Core utility 'utils.py' not found. App cannot function.", icon="🚨")
    st.stop()

PDFComparator = BaseComparator
GroqPDFComparator = BaseComparator
basic_comparator_available = False
llm_comparator_available = False


try:
    from comparator import PDFComparator as BasicComp
    if hasattr(BasicComp, '_generate_word_diff_html') and callable(getattr(BasicComp, 'compare')):
        PDFComparator = BasicComp
        basic_comparator_available = True
        print("Enhanced Basic comparator loaded successfully.")
    else:
         print("Basic comparator module found but lacks expected enhancements or 'compare' method.")
         basic_comparator_available = False
         st.warning("Basic comparator ('comparator.py') found but seems outdated or invalid.", icon="⚠️")

except ImportError as e:
    basic_comparator_available = False
    st.warning(f"Basic comparator ('comparator.py') not found: {e}", icon="⚠️")
    print(f"Basic comparator not found: {e}")

try:
    from llm_comparator import GroqPDFComparator as LLMComp
    if hasattr(LLMComp, 'compare') and callable(getattr(LLMComp, 'compare')):
        GroqPDFComparator = LLMComp
        llm_comparator_available = True
        print("LLM comparator loaded successfully.")
    else:
         print("LLM comparator module found but lacks 'compare' method.")
         llm_comparator_available = False
         st.warning("LLM comparator ('llm_comparator.py') found but seems invalid.", icon="⚠️")

except ImportError as e:
    llm_comparator_available = False
    st.warning(f"LLM comparator ('llm_comparator.py') not found or dependency error: {e}.", icon="⚠️")
    print(f"LLM comparator not found or error: {e}")


st.set_page_config(layout="wide", page_title="DocuDiff", page_icon="📄")
load_dotenv()

GROQ_API_KEY = ""
api_key_source_msg = "API Key Status: <span style='color: red;'>Missing</span>"

def update_key_status():
    global GROQ_API_KEY, api_key_source_msg
    env_key = os.environ.get("GROQ_API_KEY", "")
    session_key = st.session_state.get('groq_api_key', "")

    if env_key:
        GROQ_API_KEY = env_key
        st.session_state['groq_api_key'] = GROQ_API_KEY
        status_text = "Loaded from Environment"
        status_color = "green"
    elif session_key:
        GROQ_API_KEY = session_key
        status_text = "Using provided key"
        status_color = "blue"
    else:
        GROQ_API_KEY = ""
        status_text = "Missing"
        status_color = "red"
    api_key_source_msg = f"API Key Status: <span style='color: {status_color};'>{status_text}</span>"

update_key_status()


st.markdown("""
<style>
    /* Base Styles */
    .main { padding: 1rem 2rem; }
    h1, h2, h3 { color: #2c3e50; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; }

    /* Summary Card & Metrics */
    .summary-card { background-color: #f8f9fa; padding: 15px 20px; border-radius: 8px; border: 1px solid #e3e3e3; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .summary-card h3 { margin-top: 0; margin-bottom: 15px; color: #495057; font-size: 1.2em; }
    .summary-card p { margin-bottom: 5px; font-size: 1em; color: #212529; } .summary-card span { font-weight: bold; margin-right: 8px; }
    [data-testid="stMetricValue"] { font-size: 1.8em; color: #2c3e50; }
    [data-testid="stMetricLabel"] { font-size: 1em; color: #4a6f8a; padding-bottom: 5px;}

    /* Legends */
    .legend span, .legend-llm span { padding: 3px 6px; border-radius: 4px; font-family: monospace; margin: 2px 4px 2px 0; display: inline-block; border: 1px solid #ccc; color: #000 !important; font-size: 0.9em; vertical-align: middle;}
    .legend small, .legend-llm small { display: block; margin-top: 8px; color: #6c757d; font-style: italic; font-size: 0.9em;}
    .legend .diff-marker, .legend-llm .marker { display: inline-block; width: 1em; text-align: center; margin-right: 3px; font-weight: bold;}

    /* Basic Diff Styles */
    .diff-line { padding: 1px 5px; margin:0; display: block; white-space: pre-wrap; border-radius: 3px; font-family: monospace; line-height: 1.5; border: 1px solid transparent; color: #000 !important; }
    .diff-marker { display: inline-block; width: 1em; text-align: center; margin-right: 5px; font-weight: bold; user-select: none; }
    .diff-equal { background-color: #ffffff; } .diff-equal .diff-marker { opacity: 0.5; }
    .diff-added { background-color: #e6ffed; border-color: #c3e6cb; } .diff-added .diff-marker { color: #28a745; }
    .diff-deleted { background-color: #ffeef0; /* text-decoration: line-through; */ border-color: #f5c6cb; } .diff-deleted .diff-marker { color: #dc3545; }
    .diff-modified { background-color: #fffbe6; border-color: #ffeeba; } .diff-modified .diff-marker { color: #ffc107; } /* Yellowish background, asterisk marker */
    .diff-line a { color: #007bff; text-decoration: none; border-bottom: 1px dotted #007bff;} .diff-line a:hover { color: #0056b3; border-bottom-style: solid;}

    /* Word Level Diff Styles (Used by Basic diff-modified lines) */
     .word-added { background-color: #a6f3b8; border-radius: 3px; padding: 0 2px; display: inline; /* More visible green */ }
     .word-deleted { background-color: #f8a0a8; text-decoration: line-through; border-radius: 3px; padding: 0 2px; display: inline; /* More visible red */ }

    /* LLM Specific Word Styles */
     .llm-word { white-space: pre-wrap; padding: 1px 2px; margin: 0 1px; border-radius: 3px; line-height: 1.6; font-family: monospace; display: inline; color: #000 !important; }
     .status-equal { background-color: transparent; } /* LLM equal has no background */
     .status-added { background-color: #e6ffed; border: 1px solid #b7ebc0; }
     .status-deleted { background-color: #ffeef0; text-decoration: line-through; border: 1px solid #f1b0b7; }
     .status-modified { background-color: #fff3cd; border: 1px solid #ffeeba; }

    /* LLM Legend Specific Styles */
    .legend-llm .status-added { background-color: #e6ffed; border-color: #b7ebc0;}
    .legend-llm .status-deleted { background-color: #ffeef0; text-decoration: line-through; border-color: #f1b0b7;}
    .legend-llm .status-modified { background-color: #fff3cd; border-color: #ffeeba;}
    .legend-llm .status-equal { background-color: transparent; border-color: #ccc;}

    /* Diff Containers */
    .diff-container, .diff-llm-container {
        border: 1px solid #dee2e6; padding: 15px; border-radius: 5px;
        background-color: #ffffff; max-height: 65vh;
        overflow-y: auto; box-shadow: inset 0 1px 3px rgba(0,0,0,0.05);
        white-space: pre-wrap;
        font-family: monospace; line-height: 1.6; color: #000;
        font-size: 0.95em;
    }
    .diff-llm-container-inner { white-space: pre-wrap; color: #000; }

</style>
""", unsafe_allow_html=True)

st.title("📄 DocuDiff: PDF & Text Comparison")
st.markdown("Compare document versions using standard `difflib` (with word-level diff) or advanced Groq LLM analysis.")
st.divider()

with st.sidebar:
    st.header("⚙️ Configuration")

    with st.expander("Basic Comparison Options", expanded=True):
        if basic_comparator_available:
            opt_ignore_case = st.checkbox("Ignore Case", key="basic_ignore_case", value=False, help="Perform case-insensitive comparison.")
            opt_ignore_punctuation = st.checkbox("Ignore Punctuation", key="basic_ignore_punctuation", value=False, help="Remove punctuation before comparing.")
            opt_dehyphenate = st.checkbox("Attempt Dehyphenation", key="basic_dehyphenate", value=True, help="Try to join words split by hyphens across lines.")
        else:
            st.caption("Basic comparator options unavailable.")
    st.markdown("---")
    with st.expander("LLM Settings", expanded=True):
        if not llm_comparator_available:
            st.warning("LLM Comparator module not loaded.", icon="⚠️")
        else:
            if not GROQ_API_KEY:
                with st.form("api_key_form"):
                    key_input = st.text_input("Enter Groq API Key:", type="password", key="groq_api_key_input_sidebar", help="Required for LLM.")
                    submitted = st.form_submit_button("Save Key")
                    if submitted and key_input:
                        st.session_state['groq_api_key'] = key_input
                        update_key_status()
                        st.success("API Key saved for this session!")
                        st.rerun()
                    elif submitted:
                        st.warning("Please enter an API key.")
            st.markdown(api_key_source_msg, unsafe_allow_html=True)
            if GROQ_API_KEY and "provided key" in api_key_source_msg:
                st.caption("Key stored temporarily in session state.")

            GROQ_MODELS = [
                "gemma2-9b-it","llama-3.3-70b-versatile","llama-3.1-8b-instant","llama3-70b-8192","llama3-8b-8192",
                "meta-llama/llama-4-scout-17b-16e-instruct","meta-llama/llama-4-maverick-17b-128e-instruct",
                "qwen-2.5-32b","deepseek-r1-distill-qwen-32b","deepseek-r1-distill-llama-70b"
            ]
            DEFAULT_MODEL = "llama3-70b-8192"
            default_index = GROQ_MODELS.index(DEFAULT_MODEL) if DEFAULT_MODEL in GROQ_MODELS else 0
            selected_model = st.selectbox("Choose Groq Model:", GROQ_MODELS, index=default_index,
                                          key="selected_groq_model", help="Select LLM model.",
                                          disabled=not llm_comparator_available)

            # Chunk Size
            max_chunk_tokens = st.number_input("LLM: Max Tokens per Chunk:", 500, 8000, 2000, 100,
                                               key="max_chunk_tokens", help="Max tokens per API call.",
                                               disabled=not llm_comparator_available)
            st.info(f"LLM Ready: `{selected_model}` | Chunk Tokens: {max_chunk_tokens}", icon="🧠")

    st.markdown("---")
    st.header("ℹ️ About Methods")
    st.markdown("""
    **Basic (`difflib`):**
    *   Compares texts line by line after optional cleaning (case, punctuation, dehyphenation).
    *   Fast and good for structured text.
    *   Highlights added (`+`), deleted (`-`), and modified (`*`) lines.
    *   **Modified lines show word-level changes:** <span class='word-added' style='padding: 1px 3px;'>Added Word</span> / <span class='word-deleted' style='padding: 1px 3px;'>Deleted Word</span>.

    **LLM (Groq):**
    *   Uses AI to understand text structure and identify semantic changes.
    *   Highlights *word-level* changes within modified blocks:
        *   <span class='llm-word status-added'>Green</span>: Added text.
        *   <span class='llm-word status-deleted'>Red</span>: Deleted text.
        *   <span class='llm-word status-modified'>Yellow</span>: Replaced/modified text.
    *   Slower, requires API key, better for prose.
    """, unsafe_allow_html=True)
    st.markdown("---")
    st.caption(f"DocuDiff | Basic: {'✅ Available' if basic_comparator_available else '⚠️ Unavailable'} | LLM: {'✅ Available' if llm_comparator_available else '⚠️ Unavailable'}")


# --- Main Area ---
# File Upload Section
with st.container(border=True):
    st.subheader("📁 Upload Documents")
    col1, col2 = st.columns(2)
    with col1: file_1 = st.file_uploader("Document 1 (Original / Old Version)",
                                         type=["pdf", "txt"], key="file_1",
                                         help="Upload the first document (PDF or TXT).")
    with col2: file_2 = st.file_uploader("Document 2 (Revised / New Version)",
                                         type=["pdf", "txt"], key="file_2",
                                         help="Upload the second document (PDF or TXT).")

st.divider()
button_col1, button_col2 = st.columns(2)
files_ready = file_1 and file_2
llm_ready = files_ready and llm_comparator_available and bool(GROQ_API_KEY)

with button_col1:
    basic_compare_button = st.button("📊 Compare Basic (`difflib`)",
                                     use_container_width=True,
                                     disabled=not (files_ready and basic_comparator_available),
                                     type="secondary")
with button_col2:
    llm_compare_button = st.button("🧠 Compare with LLM (Groq)",
                                   use_container_width=True,
                                   disabled=not llm_ready, type="primary")

    if files_ready and llm_comparator_available and not GROQ_API_KEY:
        st.warning("Groq API Key needed in sidebar for LLM comparison.", icon="🔑")

if 'last_comparison_result' not in st.session_state: st.session_state.last_comparison_result = None
if 'last_method' not in st.session_state: st.session_state.last_method = None
if 'comparison_running' not in st.session_state: st.session_state.comparison_running = False

comparator: Optional[Any] = None

if basic_compare_button and not st.session_state.comparison_running:
    if not basic_comparator_available: st.error("Basic Comparator module not available or failed to load correctly."); st.stop()
    st.session_state.comparison_running = True
    st.session_state.last_method = "basic"
    st.session_state.last_comparison_result = None
    with st.spinner("Performing basic comparison..."):
        try:
            options = {
                "ignore_case": st.session_state.get("basic_ignore_case", False),
                "ignore_punctuation": st.session_state.get("basic_ignore_punctuation", False),
                "de_hyphenate": st.session_state.get("basic_dehyphenate", True)
            }
            comparator_instance = PDFComparator(file_1, file_2, **options)
            process_finished = comparator_instance.compare()
            st.session_state.last_comparison_result = comparator_instance
        except Exception as e:
            st.error(f"Error during basic comparison execution: {e}")
            error_result = BaseComparator()
            error_result.success = False
            error_result.error_message = f"Execution Error: {e}"
            st.session_state.last_comparison_result = error_result
    st.session_state.comparison_running = False
    st.rerun()

elif llm_compare_button and not st.session_state.comparison_running:
    if not llm_comparator_available: st.error("LLM Comparator module not loaded or failed to load correctly."); st.stop()
    if not GROQ_API_KEY: st.error("Groq API Key missing. Please provide it in the sidebar."); st.stop()

    st.session_state.comparison_running = True
    st.session_state.last_method = "llm"; st.session_state.last_comparison_result = None
    current_selected_model = st.session_state.selected_groq_model
    current_max_tokens = st.session_state.max_chunk_tokens

    try:
        client = Groq(api_key=GROQ_API_KEY)
        llm_comparator_instance = GroqPDFComparator(file_1, file_2, client,
                                                    current_selected_model, current_max_tokens)

        with st.spinner(f"Comparing using LLM ({current_selected_model})... This may take time."):
            start_comp_time = time.time()
            process_finished = llm_comparator_instance.compare()
            end_comp_time = time.time()
            st.session_state.comparison_time = end_comp_time - start_comp_time
            st.session_state.last_comparison_result = llm_comparator_instance

    except Exception as e:
        st.error(f"Failed to initialize or run LLM comparison: {e}")
        error_result = BaseComparator()
        error_result.success = False
        error_result.error_message = f"Initialization/Run Error: {e}"
        st.session_state.last_comparison_result = error_result

    st.session_state.comparison_running = False
    st.rerun()

st.divider()
st.subheader("📊 Comparison Results")

comparator_result = st.session_state.get('last_comparison_result')
method_used = st.session_state.get('last_method')

if comparator_result:
    info_message = f"Displaying results from **{method_used.upper()}** comparison."
    if method_used == 'llm' and hasattr(st.session_state, 'comparison_time'):
        info_message += f" (Completed in {st.session_state.comparison_time:.2f}s)"
    is_success = getattr(comparator_result, 'success', False)
    st.info(info_message, icon="✅" if is_success else "❌")

    if not is_success:
        err_msg = getattr(comparator_result, 'error_message', 'An unknown error occurred during comparison.')
        st.error(f"Comparison Failed: {err_msg}")

    elif getattr(comparator_result, 'is_identical_raw', False):
        st.success("✅ Documents are identical (based on raw text extraction).")

    elif getattr(comparator_result, 'is_identical', False): # Covers basic & potentially LLM if it sets this
        st.success("✅ Documents are identical (after preprocessing/analysis).")

    elif method_used == 'llm' and is_success and not getattr(comparator_result, 'all_change_blocks', True):
         st.success("✅ LLM analysis completed successfully and found no differences.")

    elif is_success:
        has_basic_diff = method_used == 'basic' and getattr(comparator_result, 'diff_html', None)
        has_llm_rendered_diff = method_used == 'llm' and getattr(comparator_result, 'rendered_html', None)
        llm_found_blocks = method_used == 'llm' and getattr(comparator_result, 'all_change_blocks', [])

        if not (has_basic_diff or has_llm_rendered_diff):
            if method_used == 'llm' and llm_found_blocks:
                 st.warning("LLM found differences, but failed to render the comparison view. Check Debug logs.")
            else:
                 st.warning("Comparison complete, but no visual differences were generated (may indicate only whitespace changes or minor differences ignored by preprocessing).")
            if hasattr(comparator_result, 'error_message') and comparator_result.error_message:
                 st.warning(f"Details: {comparator_result.error_message}")
        else:
            tab_titles = ["📈 Summary", "↔️ Comparison View", "📄 Extracted Text"]
            if method_used == 'llm':
                 tab_titles.append("🐞 LLM Debug")

            summary_tab, view_tab, text_tab, *debug_tab_list = st.tabs(tab_titles)

            with summary_tab:
                summary = getattr(comparator_result, 'summary', {})
                if not summary and is_success and not getattr(comparator_result, 'is_identical', False):
                     st.warning("Summary data is unexpectedly empty despite reported differences.")
                elif method_used == 'basic':
                    st.subheader("Basic Diff Summary (Line-based)")
                    add_count = summary.get('lines_added', 0)
                    del_count = summary.get('lines_deleted', 0)
                    mod_count = summary.get('lines_modified', 0)
                    if add_count == 0 and del_count == 0 and mod_count == 0 and not getattr(comparator_result, 'is_identical', False):
                         st.info("Summary shows no line changes based on diff opcodes. Differences might be within lines (word-level only) or whitespace.")
                    sum_cols = st.columns(3)
                    with sum_cols[0]: st.metric("Lines Added (+)", f"{add_count}")
                    with sum_cols[1]: st.metric("Lines Deleted (-)", f"{del_count}")
                    with sum_cols[2]: st.metric("Lines Modified (*)", f"{mod_count}") # Changed label
                    if mod_count > 0: st.caption("Modified lines contain word-level differences highlighted below.")
                elif method_used == 'llm':
                    st.subheader("LLM Diff Summary (Net Change & Block based)")
                    sum_cols = st.columns(4)
                    with sum_cols[0]: st.metric("Net Chars Added", f"➕ {summary.get('added_chars', 0):,}")
                    with sum_cols[1]: st.metric("Net Chars Deleted", f"➖ {summary.get('deleted_chars', 0):,}")
                    with sum_cols[2]: st.metric("Modified Blocks", f"🔄 {summary.get('modified_blocks', 0):,}")
                    with sum_cols[3]: st.metric("Modified Chars (New)", f"🎨 {summary.get('modified_chars', 0):,}")
                    st.caption("Character counts reflect net changes. 'Modified Chars (New)' counts chars in the 'new' text of modified blocks.")

            with view_tab:
                st.subheader("Detailed Differences")
                if method_used == 'basic' and has_basic_diff:
                    st.markdown(f"""
                    <div class='legend'>
                        <span class='diff-added'><span class='diff-marker'>+</span>Added Line</span>
                        <span class='diff-deleted'><span class='diff-marker'>-</span>Deleted Line</span>
                        <span class='diff-modified'><span class='diff-marker'>*</span>Modified Line</span>
                        <span class='diff-equal'><span class='diff-marker'> </span>Unchanged Line</span>
                        <span class='word-added' style='padding: 1px 3px;'>Added Word</span>
                        <span class='word-deleted' style='padding: 1px 3px;'>Deleted Word</span>
                        <small>Word diff shown within modified (*) lines. Preprocessing options affect comparison.</small>
                    </div> <hr>
                    """, unsafe_allow_html=True)
                    st.markdown(f"<div class='diff-container'>{comparator_result.diff_html}</div>", unsafe_allow_html=True)

                elif method_used == 'llm' and has_llm_rendered_diff:
                    st.markdown(f"""
                    <div class='legend-llm'>
                        <span class='status-added'>Added Text</span>
                        <span class='status-deleted'>Deleted Text</span>
                        <span class='status-modified'>Modified Text</span>
                        <span class='status-equal'>Unchanged Text</span>
                        <small>Word-level diff within modified blocks. Unchanged text has no background highlight.</small>
                    </div> <hr>
                    """, unsafe_allow_html=True)
                    st.markdown(f"<div class='diff-llm-container'>{comparator_result.rendered_html}</div>", unsafe_allow_html=True)
                elif method_used == 'llm' and is_success: # LLM ran successfully, but no rendered_html
                     st.warning("LLM comparison view could not be rendered (potentially due to rendering error after successful API calls). Check debug logs.")


            with text_tab:
                st.subheader("Raw Extracted Text (Before Preprocessing)")
                txt_col1, txt_col2 = st.columns(2)
                text1_val = getattr(comparator_result, 'text1_raw', "N/A") or "(Empty)"
                text2_val = getattr(comparator_result, 'text2_raw', "N/A") or "(Empty)"
                file1_name = getattr(file_1, 'name', 'doc1') if file_1 else 'doc1'
                file2_name = getattr(file_2, 'name', 'doc2') if file_2 else 'doc2'

                with txt_col1:
                    st.text_area(f"Document 1: {file1_name}", text1_val, height=400, key="text1_area_main", help="Raw text extracted from Document 1.")
                    st.download_button(
                        label="📥 Download Text 1",
                        data=text1_val.encode('utf-8') if text1_val != "(Empty)" else b'',
                        file_name=f"{os.path.splitext(file1_name)[0]}_extracted.txt",
                        mime="text/plain"
                    )
                with txt_col2:
                    st.text_area(f"Document 2: {file2_name}", text2_val, height=400, key="text2_area_main", help="Raw text extracted from Document 2.")
                    st.download_button(
                        label="📥 Download Text 2",
                        data=text2_val.encode('utf-8') if text2_val != "(Empty)" else b'',
                        file_name=f"{os.path.splitext(file2_name)[0]}_extracted.txt",
                        mime="text/plain"
                    )

            if debug_tab_list:
                with debug_tab_list[0]:
                    st.subheader("LLM API Call Logs & Debug Info")
                    debug_logs = getattr(comparator_result, 'debug_logs', [])
                    if debug_logs:
                         log_count = getattr(comparator_result, 'api_call_counter', len(debug_logs)) # Use counter if available
                         st.info(f"Displaying logs for {log_count} API call(s) attempted.")
                         # Ensure logs is a list of tuples/lists with 2 elements
                         if isinstance(debug_logs, list) and all(isinstance(item, (list, tuple)) and len(item) == 2 for item in debug_logs):
                             for i, log_entry in enumerate(debug_logs):
                                 prompt, response_or_error = log_entry
                                 st.markdown(f"--- **Call {i + 1}** ---")
                                 with st.expander(f"Prompt {i+1}", expanded=False):
                                     st.code(prompt, language='text')
                                 st.text("Response / Status:")
                                 is_json_like = isinstance(response_or_error, str) and (response_or_error.strip().startswith('{') or response_or_error.strip().startswith('['))
                                 lang = 'json' if 'Success' in str(response_or_error) and is_json_like else 'text'
                                 st.code(response_or_error, language=lang)
                         else:
                              st.error("Debug logs are not in the expected format (list of pairs).")
                              st.json(debug_logs)

                    elif not is_success and hasattr(comparator_result, 'error_message'):
                        st.warning(f"Comparison failed, no specific debug logs recorded. Error: {comparator_result.error_message}")
                    elif is_success:
                        st.info("No debug logs recorded (comparison might have succeeded without API calls or logging failed).")
                    else:
                         st.info("No debug logs available for this comparison.")

    elif not is_success and hasattr(comparator_result, 'error_message'):
         pass
    else:
        st.warning("Could not display comparison results due to an unexpected state or missing data.")

elif not st.session_state.comparison_running:
    st.info("⬆️ Upload two documents (PDF or TXT) in the section above and click a comparison button.")