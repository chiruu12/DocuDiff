import difflib
import html
import re
import string
from typing import List, Dict, Tuple, Optional
from utils import extract_text_from_file

class PDFComparator:
    """
    Performs basic comparison using difflib, enhanced with preprocessing options
    and word-level highlighting within changed lines.
    """
    def __init__(self, file_obj_1, file_obj_2,
                 ignore_case: bool = False,
                 ignore_punctuation: bool = False,
                 de_hyphenate: bool = False):
        """
        Initializes the comparator with file objects and comparison options.

        Args:
            file_obj_1: Uploaded file object for the first document.
            file_obj_2: Uploaded file object for the second document.
            ignore_case: If True, performs case-insensitive comparison.
            ignore_punctuation: If True, removes punctuation before comparison.
            de_hyphenate: If True, attempts to join words split by hyphens across lines.
        """
        self.file_obj_1 = file_obj_1
        self.file_obj_2 = file_obj_2
        self.ignore_case = ignore_case
        self.ignore_punctuation = ignore_punctuation
        self.de_hyphenate = de_hyphenate

        self.success: bool = False
        self.error_message: Optional[str] = None
        self.is_identical: bool = False
        self.is_identical_raw: bool = False
        self.text1_raw: Optional[str] = None
        self.text2_raw: Optional[str] = None
        self.text1_processed_lines: Optional[List[str]] = None
        self.text2_processed_lines: Optional[List[str]] = None
        self.diff_html: Optional[str] = None
        self.summary: Dict[str, int] = {"lines_added": 0, "lines_deleted": 0, "lines_modified": 0}

    def _apply_preprocessing_options(self, text: str) -> str:
        """Applies selected preprocessing options to a text string."""
        if self.ignore_case:
            text = text.lower()
        if self.ignore_punctuation:
            translator = str.maketrans('', '', string.punctuation)
            text = text.translate(translator)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _preprocess_text(self, raw_text: Optional[str]) -> Optional[List[str]]:
        """
        Preprocesses raw text into a list of cleaned lines, applying options.
        Handles de hyphenation if enabled.
        """
        if raw_text is None: return None

        processed_text = raw_text

        if self.de_hyphenate:
            processed_text = re.sub(r'-\s*\n\s*', '', processed_text)

        lines = processed_text.splitlines()

        processed_lines = []
        for line in lines:
            processed_line = self._apply_preprocessing_options(line)
            if processed_line:
                processed_lines.append(processed_line)

        return processed_lines

    @staticmethod
    def _generate_word_diff_html(line1: str, line2: str) -> str:
        """Generates HTML for word-level diff between two lines."""
        words1 = re.split(r'(\s+)', line1); words1 = [w for w in words1 if w]
        words2 = re.split(r'(\s+)', line2); words2 = [w for w in words2 if w]

        matcher = difflib.SequenceMatcher(None, words1, words2, autojunk=False)
        html_out = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            seg1 = "".join(words1[i1:i2])
            seg2 = "".join(words2[j1:j2])
            escaped1 = html.escape(seg1)
            escaped2 = html.escape(seg2)

            if tag == 'equal':
                html_out.append(escaped2)

            elif tag == 'delete':
                html_out.append(f"<span class='word-deleted'>{escaped1}</span>")

            elif tag == 'insert':
                html_out.append(f"<span class='word-added'>{escaped2}</span>")

            elif tag == 'replace':
                if escaped1.strip():
                     html_out.append(f"<span class='word-deleted'>{escaped1}</span>")

                if escaped2.strip():
                     html_out.append(f"<span class='word-added'>{escaped2}</span>")

        return "".join(filter(None, html_out))

    @staticmethod
    def _format_links(line: str) -> str:
        url_pattern = re.compile(r"((?:https?://|ftp://|www\.)[^\s/$.?#].[^\s]*)")
        parts: List[str] = []; last_end = 0
        for match in url_pattern.finditer(line):
            start, end = match.span()
            parts.append(html.escape(line[last_end:start]))
            url = match.group(1); href = url
            if url.startswith('www.') and not url.startswith(('http://', 'https://', 'ftp://')):
                href = f'http://{url}'

            safe_href = html.escape(href); safe_url_display = html.escape(url)
            parts.append(f'<a href="{safe_href}" target="_blank" title="Open link: {safe_href}">{safe_url_display}</a>')
            last_end = end

        parts.append(html.escape(line[last_end:]))
        return "".join(parts)

    def _generate_diff_html_with_word_level(self, text1_lines: List[str], text2_lines: List[str]) -> str:
        """Generates HTML diff, using word-level diff for replaced lines."""
        d = difflib.SequenceMatcher(None, text1_lines, text2_lines, autojunk=False)
        html_out: List[str] = []
        lines_added = 0
        lines_deleted = 0
        lines_modified = 0

        for opcode, i1, i2, j1, j2 in d.get_opcodes():
            if opcode == 'equal':
                for line in text1_lines[i1:i2]:
                    escaped_line = html.escape(line)
                    linked_line = self._format_links(escaped_line)
                    html_out.append(f"<span class='diff-line diff-equal'><span class='diff-marker'> </span>{linked_line}</span>")
            elif opcode == 'insert':
                for line in text2_lines[j1:j2]:
                    escaped_line = html.escape(line)
                    linked_line = self._format_links(escaped_line)
                    html_out.append(f"<span class='diff-line diff-added'><span class='diff-marker'>+</span>{linked_line}</span>")
                    lines_added += 1
            elif opcode == 'delete':
                for line in text1_lines[i1:i2]:
                    escaped_line = html.escape(line)
                    linked_line = self._format_links(escaped_line)
                    html_out.append(f"<span class='diff-line diff-deleted'><span class='diff-marker'>-</span>{linked_line}</span>")
                    lines_deleted += 1
            elif opcode == 'replace':
                len1 = i2 - i1
                len2 = j2 - j1
                lines_modified += max(len1, len2)

                max_len = max(len1, len2)
                for i in range(max_len):
                    line1 = text1_lines[i1 + i] if i < len1 else ""
                    line2 = text2_lines[j1 + i] if i < len2 else ""

                    if line1 and line2:
                        word_diff_content = self._generate_word_diff_html(line1, line2)

                        html_out.append(f"<span class='diff-line diff-modified'><span class='diff-marker'>*</span>{word_diff_content}</span>")

                    elif line2:
                        escaped_line = html.escape(line2)
                        linked_line = self._format_links(escaped_line)
                        html_out.append(f"<span class='diff-line diff-added'><span class='diff-marker'>+</span>{linked_line}</span>")

                    elif line1:
                        escaped_line = html.escape(line1)
                        linked_line = self._format_links(escaped_line)
                        html_out.append(f"<span class='diff-line diff-deleted'><span class='diff-marker'>-</span>{linked_line}</span>")

        self.summary = {"lines_added": lines_added, "lines_deleted": lines_deleted, "lines_modified": lines_modified}
        print(f"DEBUG comparator.py: Calculated summary: {self.summary}")
        return "\n".join(html_out)

    def compare(self) -> bool:
        """Compares files using configured options, returns True if process completed."""
        print(f"Starting Basic Comparison Process... Options: Case={self.ignore_case}, Punctuation={self.ignore_punctuation}, Dehyphenate={self.de_hyphenate}")
        self.success = False; self.error_message = None; self.is_identical = False
        self.is_identical_raw = False; self.diff_html = None
        self.summary = {"lines_added": 0, "lines_deleted": 0, "lines_modified": 0}
        self.text1_raw = None; self.text2_raw = None
        self.text1_processed_lines = None; self.text2_processed_lines = None

        try:
            self.text1_raw, err1 = extract_text_from_file(self.file_obj_1)
            if err1:
                self.error_message = f"Error in Document 1: {err1}"
                return False

            self.text2_raw, err2 = extract_text_from_file(self.file_obj_2)
            if err2:
                self.error_message = f"Error in Document 2: {err2}"
                return False

            if self.text1_raw is None or self.text2_raw is None:
                 self.error_message = "Text extraction failed unexpectedly."
                 return False

            raw_check_possible = not (self.ignore_case or self.ignore_punctuation or self.de_hyphenate)
            if raw_check_possible and self.text1_raw == self.text2_raw:
                self.is_identical_raw = True
                self.is_identical = True
                self.success = True
                print("Basic compare: Files identical raw (no options enabled).")
                return True

            self.text1_processed_lines = self._preprocess_text(self.text1_raw)
            self.text2_processed_lines = self._preprocess_text(self.text2_raw)
            if self.text1_processed_lines is None or self.text2_processed_lines is None:
                 self.error_message = self.error_message or "Text preprocessing failed."
                 return False

            if self.text1_processed_lines == self.text2_processed_lines:
                self.is_identical = True
                self.success = True
                self.is_identical_raw = raw_check_possible and self.is_identical_raw
                print("Basic compare: Files identical after preprocessing.")
                return True

            if self.is_identical_raw and not self.is_identical:
                 print("Warning: Raw text was identical, but processed text differs.")

            self.diff_html = self._generate_diff_html_with_word_level(
                self.text1_processed_lines, self.text2_processed_lines
            )
            self.success = True
            print("Basic compare: Differences found and diff generated.")
            return True

        except Exception as e:
             self.error_message = f"Unexpected error during basic comparison: {e}"
             self.success = False
             print(f"ERROR in basic compare: {e}")
             return True