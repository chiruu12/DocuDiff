import time
import json
import html
import re
import difflib
from groq import Groq, RateLimitError, APIError, BadRequestError
from typing import List, Dict, Tuple, Optional, Any
from utils import extract_text_from_file

try:
    import tiktoken
    tiktoken_found = True
    try:
        tokenizer = tiktoken.get_encoding("cl100k_base")
    except Exception as e:
        print(f"Warning: Could not initialize Tiktoken tokenizer: {e}")
        tiktoken_found = False
except ImportError:
    tiktoken_found = False
    tokenizer = None

class GroqPDFComparator:
    """
    Compares two documents using Groq LLM API to identify semantic changes.
    Handles text extraction, chunking, API calls, and renders word-level diffs.
    """
    DEFAULT_MODEL = "llama3-8b-8192"

    def __init__(self, pdf_file_obj_1: Any, pdf_file_obj_2: Any, groq_client: Groq,
                 model_name: str = DEFAULT_MODEL, max_chunk_tokens: int = 2000):
        """
        Initializes the LLM comparator.

        Args:
            pdf_file_obj_1: Uploaded file object for the first document.
            pdf_file_obj_2: Uploaded file object for the second document.
            groq_client: An initialized Groq API client instance.
            model_name: The name of the Groq model to use.
            max_chunk_tokens: Maximum tokens per chunk for LLM processing.
        """
        if not tiktoken_found or tokenizer is None:
            raise ImportError("Tiktoken library is required and must initialize correctly for LLM comparison.")

        self.pdf_file_obj_1 = pdf_file_obj_1
        self.pdf_file_obj_2 = pdf_file_obj_2
        self.groq_client = groq_client
        self.model_name = model_name if model_name else self.DEFAULT_MODEL
        self.max_chunk_tokens = max(max_chunk_tokens, 500)

        self.success: bool = False
        self.error_message: Optional[str] = None
        self.is_identical_raw: bool = False
        self.text1_raw: Optional[str] = None
        self.text2_raw: Optional[str] = None
        self.all_change_blocks: List[Dict] = []
        self.rendered_html: Optional[str] = None
        self.summary: Dict = self._get_default_summary()
        self.api_call_counter: int = 0
        self.debug_logs: List[Tuple[str, str]] = []

    @staticmethod
    def _get_default_summary() -> Dict:
        """Returns the default structure for the summary."""
        return {"added_chars": 0, "deleted_chars": 0, "modified_blocks": 0, "modified_chars": 0}

    def _chunk_text_by_tokens(self, text: str) -> List[str]:
        """Chunks text into pieces smaller than max_chunk_tokens using Tiktoken."""
        if not text or tokenizer is None: return []

        parts = re.split(r'\n\s*\n', text.strip())
        if len(parts) <= 1:
            parts = re.split(r'(?<=[.!?])\s+', text.strip())
            if len(parts) <= 1:
                parts = text.strip().split('\n')
                if len(parts) <= 1:
                     parts = text.strip().split()

        chunks = []
        current_chunk_parts = []
        current_token_count = 0
        separator = "\n\n"
        separator_tokens = len(tokenizer.encode(separator))

        for i, part in enumerate(parts):
            part = part.strip()
            if not part: continue

            part_tokens = len(tokenizer.encode(part))

            if part_tokens > self.max_chunk_tokens:
                if current_chunk_parts:
                    chunks.append(separator.join(current_chunk_parts))
                    current_chunk_parts = []
                    current_token_count = 0

                words = part.split()
                sub_chunk = ""
                sub_chunk_tokens = 0
                for word in words:
                    word_prefix = separator if sub_chunk else ""
                    word_token_estimate = len(tokenizer.encode(word_prefix + word)) - len(tokenizer.encode(word_prefix))

                    if sub_chunk_tokens + word_token_estimate <= self.max_chunk_tokens:
                        sub_chunk += (" " if sub_chunk else "") + word
                        sub_chunk_tokens += word_token_estimate
                    else:
                        if sub_chunk: chunks.append(sub_chunk)
                        word_alone_tokens = len(tokenizer.encode(word))
                        if word_alone_tokens <= self.max_chunk_tokens:
                             sub_chunk = word
                             sub_chunk_tokens = word_alone_tokens
                        else:
                             print(f"Warning: Word exceeds max_chunk_tokens, truncating: '{word[:100]}...'")
                             encoded_word = tokenizer.encode(word)
                             truncated_word = tokenizer.decode(encoded_word[:self.max_chunk_tokens])
                             chunks.append(truncated_word)
                             sub_chunk = ""
                             sub_chunk_tokens = 0
                if sub_chunk: chunks.append(sub_chunk)
                continue

            potential_tokens = current_token_count + (separator_tokens if current_chunk_parts else 0) + part_tokens
            if potential_tokens <= self.max_chunk_tokens:
                current_chunk_parts.append(part)
                current_token_count = potential_tokens
            else:
                if current_chunk_parts:
                    chunks.append(separator.join(current_chunk_parts))
                current_chunk_parts = [part]
                current_token_count = part_tokens

        if current_chunk_parts:
            chunks.append(separator.join(current_chunk_parts))

        return [chunk for chunk in chunks if chunk.strip()]

    @staticmethod
    def _create_change_block_prompt(original_chunk: str, new_chunk: str) -> str:
        """Creates the structured prompt for the Groq API."""
        prompt = f"""
            Analyze the 'Original Text' and 'New Text' below. Identify all changes and represent them as a sequence of blocks.
            
            Your response MUST be a single, valid JSON object containing ONLY the key "change_blocks".
            The value of "change_blocks" MUST be a JSON array `[]` of block objects.
            Each block object in the array MUST have the following keys:
            - "status": A string, must be one of: "equal", "deleted", "added", "modified".
            - "text1": A string containing the relevant text from the Original Text. This MUST be an empty string "" if status is "added".
            - "text2": A string containing the relevant text from the New Text. This MUST be an empty string "" if status is "deleted".
            
            Guidelines:
            - Represent the *entire* content of both inputs through the sequence of blocks.
            - Maintain original text segments and line breaks within the "text1" and "text2" values accurately. Use `\\n` for newlines within the JSON strings if necessary.
            - Use "equal" for segments that are identical in both texts.
            - Use "deleted" where text exists in Original but not New (text2 must be "").
            - Use "added" where text exists in New but not Original (text1 must be "").
            - Use "modified" ONLY for segments that correspond conceptually but have internal changes (e.g., rephrasing, correction). Prefer "deleted" + "added" if text is completely different or unrelated.
            - Ensure the blocks cover the text sequentially without gaps or overlaps. The concatenation of 'text1' from all blocks should reconstruct the Original Text chunk, and 'text2' should reconstruct the New Text chunk.
            
            Example JSON Response Structure:
            ```json
            {{
              "change_blocks": [
                {{"status": "equal", "text1": "This part is unchanged.\\n", "text2": "This part is unchanged.\\n"}},
                {{"status": "modified", "text1": "The old sentence.", "text2": "The revised sentence."}},
                {{"status": "deleted", "text1": "This section was removed.", "text2": ""}},
                {{"status": "added", "text1": "", "text2": "This section was newly added."}},
                {{"status": "equal", "text1": " The end.", "text2": " The end."}}
              ]
            }}
            Use code with caution.
            Python
            DO NOT include any text outside the single JSON object structure (like "```json" markers or explanations) in your final output.
            --- Original Text ---
            {original_chunk}
            --- End Original Text ---
            --- New Text ---
            {new_chunk}
            --- End New Text ---
            Now, provide the JSON output:
        """
        return prompt.strip()
    def _call_groq_change_blocks(self, original_chunk: str, new_chunk: str) -> Optional[List[Dict]]:
        """Calls the Groq API, handles errors, and parses the JSON response."""
        prompt = self._create_change_block_prompt(original_chunk, new_chunk)
        raw_response_content = "Error: No response received"
        log_entry: Tuple[str, str] = (prompt, "")

        try:
            self.api_call_counter += 1
            start_time = time.time()
            print(f"Calling Groq API (Call #{self.api_call_counter})...") # Debug print
            chat_completion = self.groq_client.chat.completions.create(
                 messages=[{"role": "user", "content": prompt}],
                 model=self.model_name,
                 temperature=0.1,
                 max_tokens=8000,
                 response_format={"type": "json_object"},
            )
            end_time = time.time()
            raw_response_content = chat_completion.choices[0].message.content
            duration = end_time - start_time
            print(f"Groq API Call #{self.api_call_counter} completed in {duration:.2f}s.") # Debug print

            try:
                result = json.loads(raw_response_content)
            except json.JSONDecodeError as json_e:
                log_entry = (prompt, f"ERROR: Invalid JSON received - {json_e}\nRaw Response:\n{raw_response_content}")
                self.debug_logs.append(log_entry)
                raise ValueError(f"LLM returned invalid JSON: {json_e}") from json_e

            log_entry = (prompt, f"Success ({duration:.2f}s):\n{raw_response_content}")
            self.debug_logs.append(log_entry)


            if not isinstance(result, dict) or "change_blocks" not in result:
                raise ValueError("LLM response missing 'change_blocks' key in the root JSON object.")

            change_blocks = result["change_blocks"]
            if not isinstance(change_blocks, list):
                 raise ValueError("'change_blocks' value is not a JSON array.")

            # Validate each block structure
            validated_blocks = []
            for i, item in enumerate(change_blocks):
                if not isinstance(item, dict): raise ValueError(f"Block {i} is not a JSON object.")
                status = item.get("status")
                text1 = item.get("text1")
                text2 = item.get("text2")
                valid_statuses = ["equal", "added", "deleted", "modified"]
                if status not in valid_statuses: raise ValueError(f"Block {i} has invalid status '{status}'. Must be one of {valid_statuses}.")
                if text1 is not None and not isinstance(text1, str): raise ValueError(f"Block {i} 'text1' is not a string.")
                if text2 is not None and not isinstance(text2, str): raise ValueError(f"Block {i} 'text2' is not a string.")

                item["text1"] = item.get("text1", "") or ""
                item["text2"] = item.get("text2", "") or ""


                if status == "deleted" and item["text2"] != "":
                    print(f"Warning: Correcting block {i} ('deleted'): setting text2 to empty.")
                    item["text2"] = ""

                if status == "added" and item["text1"] != "":
                    print(f"Warning: Correcting block {i} ('added'): setting text1 to empty.")
                    item["text1"] = ""

                if status == "modified" and (not item["text1"] or not item["text2"]):
                    print(f"Warning: Block {i} ('modified') has empty text1 or text2.")

                if status == "equal" and item["text1"] != item["text2"]:
                    print(f"Warning: Block {i} ('equal') has different text1/text2.")

                validated_blocks.append(item)

            return validated_blocks

        except RateLimitError as rle:
            self.error_message = f"API Rate Limit Error: {rle}. Please wait and try again."
            print(f"Rate Limit Error: {rle}")
            log_entry = (prompt, f"ERROR: RateLimitError - {rle}")
            if log_entry not in self.debug_logs: self.debug_logs.append(log_entry)
            time.sleep(5)
            return None
        except BadRequestError as bre:
             # Often happens if the prompt + response exceeds model context or other input issues
             self.error_message = f"API Bad Request Error: {bre}. Check input size/content or model compatibility."
             print(f"Bad Request Error: {bre}")
             log_entry = (prompt, f"ERROR: BadRequestError - {bre}\nRaw Response:\n{raw_response_content}")
             if log_entry not in self.debug_logs: self.debug_logs.append(log_entry)
             return None
        except APIError as apie:
            self.error_message = f"Groq API Error ({apie.status_code}): {apie.message}"
            print(f"API Error: {apie}")
            log_entry = (prompt, f"ERROR: APIError - {apie}\nRaw Response:\n{raw_response_content}")
            if log_entry not in self.debug_logs: self.debug_logs.append(log_entry)
            return None

        except ValueError as ve:
             self.error_message = f"LLM Response Validation Error: {ve}"
             print(f"Value Error: {ve}")
             if "Invalid JSON" not in str(ve):
                 log_entry = (prompt, f"ERROR: ValueError - {ve}\nRaw Response:\n{raw_response_content}")
                 if log_entry not in self.debug_logs: self.debug_logs.append(log_entry)
             return None

        except Exception as e:
            # Catch-all for other unexpected errors during API call/processing
            self.error_message = f"Unexpected Error during API Call: {type(e).__name__} - {e}"
            print(f"Unexpected Error: {e}")
            log_entry = (prompt, f"ERROR: {type(e).__name__} - {e}\nRaw Response:\n{raw_response_content}")
            if log_entry not in self.debug_logs: self.debug_logs.append(log_entry)
            return None

    @staticmethod
    def _render_word_diff_html(text1: str, text2: str) -> str:
        """Performs word-level diff and renders HTML with specific styling."""
        words1 = re.split(r'(\s+)', text1)
        words2 = re.split(r'(\s+)', text2)

        words1 = [w for w in words1 if w]
        words2 = [w for w in words2 if w]

        word_matcher = difflib.SequenceMatcher(None, words1, words2, autojunk=False)
        modified_content_html = ""

        for tag, i1, i2, j1, j2 in word_matcher.get_opcodes():

            text1_segment = "".join(words1[i1:i2])
            text2_segment = "".join(words2[j1:j2])

            escaped1 = html.escape(text1_segment)
            escaped2 = html.escape(text2_segment)

            escaped1 = escaped1.replace('\n', '<br>\n')
            escaped2 = escaped2.replace('\n', '<br>\n')


            if tag == 'equal':
                modified_content_html += f"<span class='llm-word status-equal'>{escaped2}</span>"

            elif tag == 'delete':
                if escaped1.strip() and escaped1 != '<br>\n':
                    modified_content_html += f"<span class='llm-word status-deleted'>{escaped1}</span>"

                else:
                    modified_content_html += escaped1

            elif tag == 'insert':
                if escaped2.strip() and escaped2 != '<br>\n':
                    modified_content_html += f"<span class='llm-word status-added'>{escaped2}</span>"

                else:
                    modified_content_html += escaped2

            elif tag == 'replace':
                if escaped2.strip() and escaped2 != '<br>\n':
                     modified_content_html += f"<span class='llm-word status-modified'>{escaped2}</span>"

                elif not escaped1.strip() and escaped2:
                     modified_content_html += escaped2

                elif escaped1.strip() and not escaped2.strip():
                     modified_content_html += f"<span class='llm-word status-deleted'>{escaped1}</span>"

                elif escaped1 and escaped2:
                    modified_content_html += escaped2

        return modified_content_html

    @classmethod
    def _render_change_blocks_html(cls, change_blocks: List[Dict]) -> str:
        """Renders the list of change blocks into a single HTML string."""
        html_output_parts: List[str] = []

        for block in change_blocks:
            status = block.get("status", "equal").lower()
            text1 = block.get("text1", "")
            text2 = block.get("text2", "")

            block_html = ""

            if status == "equal":
                escaped_text = html.escape(text2).replace('\n', '<br>\n')
                if text2: block_html = f"<span class='llm-word status-equal'>{escaped_text}</span>"

            elif status == "deleted":
                escaped_text = html.escape(text1).replace('\n', '<br>\n')
                if text1: block_html = f"<span class='llm-word status-deleted'>{escaped_text}</span>"

            elif status == "added":
                 escaped_text = html.escape(text2).replace('\n', '<br>\n')
                 if text2: block_html = f"<span class='llm-word status-added'>{escaped_text}</span>"

            elif status == "modified":
                block_html = cls._render_word_diff_html(text1, text2)

            if block_html:
                html_output_parts.append(block_html)

        joined_html = "".join(html_output_parts)

        return f"<div class='diff-llm-container-inner'>{joined_html}</div>"


    def _calculate_summary(self):
        """Calculates summary statistics based on the final change blocks."""
        if not self.all_change_blocks:
            self.summary = self._get_default_summary()
            return

        total_added_chars = 0
        total_deleted_chars = 0
        modified_block_count = 0
        modified_chars_in_new = 0

        for block in self.all_change_blocks:
            status = block.get("status", "equal")
            text1 = block.get("text1", "")
            text2 = block.get("text2", "")

            if status == "added":
                total_added_chars += len(text2)

            elif status == "deleted":
                total_deleted_chars += len(text1)

            elif status == "modified":
                modified_block_count += 1
                modified_chars_in_new += len(text2)

                words1 = re.split(r'(\s+)', text1); words1 = [w for w in words1 if w]
                words2 = re.split(r'(\s+)', text2); words2 = [w for w in words2 if w]

                word_matcher = difflib.SequenceMatcher(None, words1, words2, autojunk=False)
                mod_added_net = 0
                mod_deleted_net = 0

                for tag, i1, i2, j1, j2 in word_matcher.get_opcodes():
                     seg1 = "".join(words1[i1:i2])
                     seg2 = "".join(words2[j1:j2])
                     if tag == 'insert':
                         mod_added_net += len(seg2)

                     elif tag == 'delete':
                         mod_deleted_net += len(seg1)

                     elif tag == 'replace':
                          mod_deleted_net += len(seg1)
                          mod_added_net += len(seg2)

                total_added_chars += mod_added_net
                total_deleted_chars += mod_deleted_net

        self.summary = {
            "added_chars": total_added_chars,       # Total chars added
            "deleted_chars": total_deleted_chars,   # Total chars deleted
            "modified_blocks": modified_block_count,# Count of blocks marked 'modified'
            "modified_chars": modified_chars_in_new # Chars count in the 'new' text of modified blocks
        }


    def compare(self) -> bool:
        """
        Main comparison logic: extract, chunk, call API, render.

        Returns:
            bool: True if comparison process completed (check self.success for actual outcome),
                  False if a critical error stopped the process early.
        """
        self.success = False
        self.error_message = None
        self.is_identical_raw = False
        self.all_change_blocks = []
        self.rendered_html = None
        self.summary = self._get_default_summary()
        self.debug_logs = []
        self.api_call_counter = 0
        self.text1_raw = None
        self.text2_raw = None

        print("Starting LLM Comparison Process...")

        try:
            print("Extracting text...")
            self.text1_raw, err1 = extract_text_from_file(self.pdf_file_obj_1)
            if err1:
                self.error_message = f"Error in Document 1: {err1}"
                return False

            self.text2_raw, err2 = extract_text_from_file(self.pdf_file_obj_2)
            if err2:
                self.error_message = f"Error in Document 2: {err2}"
                return False

            if self.text1_raw is None or self.text2_raw is None:
                 self.error_message = "Text extraction failed unexpectedly after checks."
                 return False

            print(f"Extracted Doc1: {len(self.text1_raw)} chars, Doc2: {len(self.text2_raw)} chars")

            if self.text1_raw == self.text2_raw:
                print("Documents are identical based on raw text.")
                self.is_identical_raw = True
                self.success = True
                return self.success

            if not self.text1_raw.strip() and not self.text2_raw.strip():
                 print("Both documents are effectively empty after extraction.")
                 self.success = True
                 return self.success

            print("Chunking text...")
            try:
                chunks1 = self._chunk_text_by_tokens(self.text1_raw)
                chunks2 = self._chunk_text_by_tokens(self.text2_raw)
                print(f"Chunked Doc1: {len(chunks1)} chunks, Doc2: {len(chunks2)} chunks")

            except Exception as e:
                self.error_message = f"Error during text chunking: {e}"
                return False

            if not chunks1 and not chunks2:
                print("Both documents produced no chunks after processing.")
                self.success = True
                return True

            num_chunks_to_process = max(len(chunks1), len(chunks2))
            print(f"Processing {num_chunks_to_process} chunk pairs...")
            self.all_change_blocks = []

            for i in range(num_chunks_to_process):
                print(f"Processing chunk pair {i+1}/{num_chunks_to_process}...")
                chunk1 = chunks1[i] if i < len(chunks1) else ""
                chunk2 = chunks2[i] if i < len(chunks2) else ""

                if not chunk1.strip() and not chunk2.strip():
                    print(f"  Skipping empty chunk pair {i+1}")
                    continue

                if not chunk1.strip() and chunk2.strip(): # Chunk added
                    print(f"  Chunk {i+1}: Added block (no API call)")
                    self.all_change_blocks.append({"status": "added", "text1": "", "text2": chunk2})
                    continue

                if chunk1.strip() and not chunk2.strip(): # Chunk deleted
                    print(f"  Chunk {i+1}: Deleted block (no API call)")
                    self.all_change_blocks.append({"status": "deleted", "text1": chunk1, "text2": ""})
                    continue

                if chunk1 == chunk2:
                    print(f"  Chunk {i+1}: Equal block (no API call)")
                    self.all_change_blocks.append({"status": "equal", "text1": chunk1, "text2": chunk2})
                    continue

                if self.api_call_counter > 0:
                    time.sleep(0.1)

                change_blocks_result = self._call_groq_change_blocks(chunk1, chunk2)

                if change_blocks_result is None:
                    print(f"  API Call for chunk {i+1} failed. Error: {self.error_message}")
                    self.success = False
                    return self.success

                self.all_change_blocks.extend(change_blocks_result)
                print(f"  Chunk {i+1}: Processed via API, {len(change_blocks_result)} blocks found.")

            print("Finished processing all chunks.")

            print("Calculating summary and rendering HTML...")
            try:
                self._calculate_summary()
                self.rendered_html = self._render_change_blocks_html(self.all_change_blocks)
                self.success = True
                print("Comparison successful.")
                return True
            except Exception as finalization_error:
                 print(f"ERROR during finalization (summary/render): {finalization_error}")
                 self.error_message = f"Error during result finalization: {finalization_error}"
                 self.success = False
                 return self.success

        except Exception as main_error:
            print(f"ERROR during main comparison process: {main_error}")
            if not self.error_message:
                self.error_message = f"Unexpected error during comparison: {type(main_error).__name__} - {main_error}"
            self.success = False
            return self.success