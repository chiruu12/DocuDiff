import fitz
import re
from io import BytesIO
from typing import Optional

def extract_text_from_file(uploaded_file):
    """
    Extracts text from an uploaded file (PDF or TXT).

    Args:
        uploaded_file: The uploaded file object from Streamlit.

    Returns:
        A tuple: (extracted_text: str | None, error_message: str | None)
    """
    if uploaded_file is None:
        return None, "Internal error: No file object provided."

    file_name = getattr(uploaded_file, 'name', 'unknown')
    file_ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
    error_message = None
    full_text = None

    try:
        file_bytes = uploaded_file.getvalue()

        if file_ext == "txt":
            try:
                full_text = file_bytes.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    full_text = file_bytes.decode('latin-1')
                    print(f"Warning: Decoded '{file_name}' as latin-1.")
                except UnicodeDecodeError:
                     return None, "Text encoding error (not UTF-8 or Latin-1)."
            full_text = full_text.replace('\r\n', '\n').replace('\r', '\n')

        elif file_ext == "pdf":
            try:
                document = fitz.open(stream=file_bytes, filetype="pdf")
                page_texts = [page.get_text("text") for page in document]
                document.close()
                full_text = "\n".join(filter(None, page_texts))
                full_text = re.sub(r'\n\s*\n+', '\n\n', full_text)
                full_text = re.sub(r' +\n', '\n', full_text)
            except Exception as pdf_e:
                if "cannot open broken document" in str(pdf_e): error_message = "Corrupted or invalid PDF."
                elif "password" in str(pdf_e).lower(): error_message = "Password-protected PDF (not supported)."
                elif "No objects found" in str(pdf_e) or "is empty" in str(pdf_e): full_text = ""
                else: error_message = f"PDF processing error: {pdf_e}"
        else:
            try:
                print(f"Attempting PDF extraction for unknown type: {file_ext}")
                document = fitz.open(stream=file_bytes, filetype="pdf")
                page_texts = [page.get_text("text") for page in document]
                document.close()
                full_text = "\n".join(filter(None, page_texts))
                full_text = re.sub(r'\n\s*\n+', '\n\n', full_text)
                full_text = re.sub(r' +\n', '\n', full_text)
                if not full_text.strip():
                     error_message = f"Unsupported file type: '{file_ext}'. Please upload PDF or TXT."
                     full_text = None
            except Exception:
                 error_message = f"Unsupported file type: '{file_ext}'. Please upload PDF or TXT."


        if full_text is not None:
            return full_text.strip(), None
        else:
            final_error = error_message or f"Could not extract text from '{file_name}'."
            return None, final_error

    except Exception as e:
        return None, f"Error processing '{file_name}': {type(e).__name__} - {e}"


class BaseComparator:
    success: bool = False
    error_message: Optional[str] = "Comparator module not loaded."
    is_identical: bool = False
    is_identical_raw: bool = False
    text1_raw: Optional[str] = None
    text2_raw: Optional[str] = None
    diff_html: Optional[str] = None
    rendered_html: Optional[str] = None
    summary: dict = {}
    all_change_blocks: list = []
    debug_logs: list = []
    api_call_counter: int = 0

    def __init__(self, *args, **kwargs):
        pass

    def compare(self) -> bool:
        print(f"WARN: Called compare() on BaseComparator placeholder for {type(self).__name__}")
        self.success = False
        return False