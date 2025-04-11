# DocuDiff: PDF & TXT Comparison Tool 📄

DocuDiff is a web-based application built with Streamlit that allows users to compare two documents (**PDF or TXT**) and visualize the differences. It offers two distinct comparison methods: a fast, line-based approach using Python's `difflib` with enhanced word-level highlighting for modifications, and a more advanced, semantic comparison using the Groq LLM API.

## ✨ Key Features

*   **PDF & TXT Support:** Compare `.pdf` and `.txt` files.
*   **Dual Comparison Methods:**
    *   **Basic (difflib):** Fast, line-oriented comparison with options to ignore case, punctuation, and dehyphenate text. Highlights added (`+`), deleted (`-`), and modified (`*`) lines. Modified lines show word-level differences (<span style='background-color: #a6f3b8; border-radius: 3px; padding: 0 2px;'>added</span> / <span style='background-color: #f8a0a8; text-decoration: line-through; border-radius: 3px; padding: 0 2px;'>deleted</span>).
    *   **LLM (Groq):** Uses large language models via the Groq API for semantic comparison, identifying added, deleted, and modified blocks of text. Provides word-level highlighting (<span style='background-color: #e6ffed; border: 1px solid #b7ebc0;'>added</span>, <span style='background-color: #ffeef0; text-decoration: line-through; border: 1px solid #f1b0b7;'>deleted</span>, <span style='background-color: #fff3cd; border: 1px solid #ffeeba;'>modified</span>) within changes.
*   **Interactive UI:** Clean and intuitive interface built with Streamlit.
*   **Side-by-Side View:** Presents comparison results clearly.
*   **Configurable Options:** Adjust preprocessing for basic diff and select different LLM models via the sidebar.
*   **Extracted Text View:** Allows users to inspect the raw text extracted from each document.
*   **API Key Handling:** Securely handles the Groq API key via environment variables or temporary session input (not stored permanently).

## 🛠️ Installation

Follow these steps to set up and run DocuDiff locally:

1.  **Prerequisites:**
    *   Python 3.8+ installed.
    *   `pip` (Python package installer).
    *   `git` (for cloning the repository).

2.  **Clone the Repository:**
    ```bash
    git clone https://github.com/chiruu12/DocuDiff.git
    cd docudiff
    ```


3.  **Install Dependencies:**
    Make sure you have the `requirements.txt` file (as shown at the top) in your project root.
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set Up Environment Variables (for LLM Comparison):**
    *   Create a file named `.env` in the root directory of the project (`docudiff/`).
    *   Add your Groq API key to this file:
        ```dotenv
        # .env
        GROQ_API_KEY="gsk_YourActualGroqApiKeyGoesHere"
        ```
    *   Replace `"gsk_YourActualGroqApiKeyGoesHere"` with your real Groq API key.
    *   **Note:** The `.env` file should be listed in `.gitignore` to prevent accidental key commits. Alternatively, you can enter the key directly in the app's sidebar each time you run it (it will be stored only for the current session).

## 🚀 Usage

1.  **Ensure Prerequisites:** Make sure you have completed the installation steps.
2.  **API Key:** Have your `.env` file set up or be ready to enter the Groq API key in the sidebar if you plan to use the LLM comparison.
3.  **Run the Streamlit App:**
    ```bash
    streamlit run ui.py
    ```
4.  **Open in Browser:** Streamlit will typically provide a local URL (e.g., `http://localhost:8501`) to open in your web browser.
5.  **Upload Documents:** Use the file uploaders to select the two documents (Original/Old and Revised/New) you want to compare. Supported formats: **PDF, TXT**.
6.  **Configure Options (Optional):**
    *   Use the sidebar to adjust options for the Basic comparison (Ignore Case, etc.).
    *   If using LLM comparison, select the desired Groq model and configure chunk size if needed. Enter the API key if not using `.env`.
7.  **Compare:** Click either the "Compare Basic" or "Compare with LLM" button.
8.  **View Results:** The comparison results will be displayed below the buttons, organized into tabs:
    *   **Summary:** High-level statistics about the changes.
    *   **Comparison View:** The detailed, highlighted differences.
    *   **Extracted Text:** The raw text extracted from each document.
    *   **LLM Debug (LLM only):** Logs from the Groq API calls (useful for troubleshooting).

## 📄 Technical Documentation

### Approach

1.  **Text Extraction (`utils.py`):**
    *   A unified function handles extraction based on file extension.
    *   **PDF:** Uses the **PyMuPDF (fitz)** library, iterating through pages and extracting text content (`page.get_text("text")`). Basic whitespace normalization is applied. Handles common PDF errors like password protection or corruption gracefully.
    *   **TXT:** Reads the file bytes and decodes using UTF-8, with a fallback to Latin-1 for common encoding issues. Normalizes line endings (`\n`).
    *   The goal is to get a clean string representation of the document's textual content for comparison.

2.  **Comparison (`comparator.py` / `llm_comparator.py`):**
    *   **Basic Method (`comparator.py`):**
        *   *Preprocessing:* Applies optional user-selected steps (case folding, punctuation removal, dehyphenation) to the extracted text before comparison to reduce noise from formatting changes.
        *   *Core Diff:* Uses Python's built-in `difflib.SequenceMatcher` to compare the *processed* lists of lines. `get_opcodes()` identifies blocks of equal, added, deleted, or replaced lines.
        *   *Word-Level Enhancement:* For lines identified by difflib as 'replace', it performs a secondary, word-level diff using `difflib` between the corresponding old and new lines.
        *   *Rendering:* Generates HTML, applying specific CSS classes (`diff-added`, `diff-deleted`, `diff-modified`, `word-added`, `word-deleted`) to lines and words based on the diff results. Modified lines get a distinct background and marker.
    *   **LLM Method (`llm_comparator.py`):**
        *   *Chunking:* Splits the extracted text from both documents into smaller chunks based on token limits using **tiktoken** (specifically `cl100k_base` encoding). This is necessary to fit within the LLM's context window. Strategy prioritizes splitting by paragraphs, then sentences, then lines, then words as fallbacks.
        *   *API Interaction:* For corresponding chunks from both documents, it constructs a detailed prompt instructing the **Groq LLM** (e.g., `llama3-8b-8192`) to identify changes and return them in a structured JSON format (`{"change_blocks": [{"status": "...", "text1": "...", "text2": "..."}]}`). Uses Groq's JSON mode for reliable output.
        *   *Response Parsing & Validation:* Parses the JSON response from the LLM. Includes validation checks to ensure the structure and status values (`equal`, `added`, `deleted`, `modified`) are correct. Attempts minor corrections (e.g., ensuring `text2` is empty for `deleted` status).
        *   *Rendering:* Iterates through the `change_blocks` received from the LLM. For blocks with `status="modified"`, it performs a word-level diff using `difflib` on the `text1` and `text2` content of that block. Generates HTML with appropriate CSS classes (`status-added`, `status-deleted`, `status-modified`) applied to words/spans based on the LLM status and the internal word diff.
    *   *Error Handling:* Includes specific error handling for API issues like rate limits (`RateLimitError`), bad requests (`BadRequestError`), and JSON decoding/validation errors.

### Libraries Chosen & Rationale

*   **Streamlit:** Chosen for its speed and ease in creating interactive web UIs directly from Python scripts, ideal for rapid prototyping and data-focused applications.
*   **Groq (`groq` package):** The official Python client for interacting with the Groq API, providing necessary methods for LLM inference. Chosen because the assignment implies using an LLM, and Groq offers fast inference.
*   **PyMuPDF (`fitz`):** A high-performance, robust library for PDF manipulation, particularly strong and reliable for text extraction compared to some alternatives. Essential for `.pdf` support.
*   **Tiktoken:** OpenAI's fast BPE tokenizer, used here for accurately counting tokens to ensure text chunks fit within the LLM's context window limits. More accurate than simple word or character counts.
*   **python-dotenv:** Standard practice for managing environment variables (like API keys) locally using `.env` files, keeping sensitive information out of the codebase.
*   **difflib:** Python's built-in library for sequence comparison. Used for the core logic of the basic comparison and for the word-level diffing within both basic and LLM methods. It's efficient and readily available.
*   **re (built-in):** Used extensively for text cleaning, normalization (whitespace), dehyphenation, and splitting text for word-level diffs.

### Challenges Faced & Solutions

1.  **Text Extraction Consistency:** PDFs vary wildly in structure. Extracting text accurately, especially preserving intended line breaks and handling tables/complex formatting, is challenging.
    *   **Solution:** Focused on extracting primary page text using PyMuPDF. Applied consistent whitespace normalization (`re.sub`) and line ending conversion (`\n`) post-extraction. Acknowledged limitations (e.g., complex tables might not render perfectly). Added dehyphenation as an option to mitigate words split across lines. TXT extraction is simpler but relies on correct decoding (UTF-8/Latin-1).
2.  **Meaningful Basic Comparison:** Simple line diffs are often too noisy due to minor formatting, case, or punctuation changes.
    *   **Solution:** Introduced preprocessing options (ignore case/punctuation, dehyphenate). Implemented word-level highlighting within lines marked as `modified` by `difflib`, making the changes much easier to spot.
3.  **LLM Reliability & Structured Output:** Getting the LLM to consistently return valid JSON in the desired structure, especially for complex diffs, required careful prompting.
    *   **Solution:** Designed a very specific prompt clearly outlining the required JSON structure, field definitions, and rules (e.g., `text1` must be empty for "added"). Used Groq's `json_object` response format. Added Python-side validation after receiving the response to catch structural errors or invalid 'status' values.
4.  **LLM Context Window Limits:** Large documents exceed the token limits of LLMs.
    *   **Solution:** Implemented a chunking strategy using `tiktoken` to split documents into manageable pieces before sending them to the LLM. The strategy attempts to preserve semantic units (paragraphs/sentences) where possible.
5.  **Diff Visualization:** Presenting the differences clearly in the UI, especially combining line-level and word-level highlighting.
    *   **Solution:** Used Streamlit's layout features (columns, tabs). Applied custom CSS to style added, deleted, and modified lines/words distinctly for both basic and LLM outputs, ensuring visual consistency where appropriate.

## 🔮 Future Improvements

*   **Advanced Preprocessing:** Integrate OCR (e.g., using Tesseract via `pytesseract`) to handle image-based PDFs. Implement more sophisticated table extraction and comparison.
*   **More File Types:** Add support for other common formats like **DOCX**, ODT, RTF, potentially HTML or source code files with syntax awareness.
*   **Enhanced Diff View:** Implement a side-by-side, synchronized scrolling view for easier comparison of longer documents.
*   **Section Ignoring:** Allow users to define patterns or regions (e.g., headers/footers, page numbers) to be ignored during comparison.
*   **Asynchronous Operations:** Make LLM API calls asynchronous (`asyncio`) to prevent the UI from freezing during long comparisons.
*   **Improved Chunk Differencing:** Explore more advanced algorithms for comparing chunked documents, potentially aligning chunks based on content similarity rather than just index (e.g., using vector embeddings or more complex diff algorithms).
*   **Testing:** Add comprehensive unit and integration tests to ensure reliability of extraction, preprocessing, comparison logic, and API interaction.
*   **Deployment:** Containerize the application using Docker for easier deployment.
