from abc import ABC, abstractmethod
from typing import Type, List, Dict, Any
import json
import logging
import time
import base64
import requests
from pydantic import BaseModel
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from core.config import config
from core.log import log_llm_start, log_llm_done

from core.usage_tracker import UsageTracker

logger = logging.getLogger(__name__)


def _is_timeout(e: Exception) -> bool:
    """Return True if the exception represents a network/API timeout."""
    if isinstance(e, requests.exceptions.Timeout):
        return True
    msg = str(e).lower()
    return any(k in msg for k in ("timeout", "timed out", "deadline exceeded"))


def _is_server_error(e: Exception) -> bool:
    """Return True if the exception represents a 5xx server-side error."""
    msg = str(e).lower()
    return any(k in msg for k in ("500", "503", "internal server error", "service unavailable", "overloaded"))

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def generate(self, prompt: str, system_instruction: str = None) -> str:
        """Generates a text response from the LLM."""
        pass

    @abstractmethod
    def generate_structured(self, prompt: str, response_model: Type[BaseModel]) -> BaseModel:
        """Generates a structured response based on a Pydantic model."""
        pass

    @abstractmethod
    def generate_with_tools(
        self,
        system_instruction: str,
        history: List[Dict[str, Any]],
        tool_declarations: List[Any],
        caller: str = "Coder",
    ) -> Dict[str, Any]:
        """Generates a response that may include tool/function calls."""
        pass

class GeminiProvider(LLMProvider):
    """Gemini implementation of the LLM provider with key rotation."""
    
    def __init__(self, model_name: str = None):
        # We check for keys dynamically in _get_model
        if not config.get_gemini_keys():
            raise ValueError("No Gemini API keys found in configuration (GEMINI_API_KEY or GEMINI_API_KEYS).")

        self.tracker = UsageTracker(
            config.GEMINI_USAGE_PATH,
            config.GEMINI_DAILY_LIMIT,
            rate_limit=config.GEMINI_RATE_LIMIT,
        )
        self.model_name = model_name or config.GEMINI_MODEL
        self.max_tokens = 8192

    def _handle_limit_error(self, error_msg: str, api_key: str):
        """
        Distinguishes between daily quota exhaustion and per-minute rate limiting.
        Updates the tracker accordingly.
        """
        msg = error_msg.lower()
        if "quota" in msg:
            logger.warning(f"Gemini API key {api_key[:6]}... QUOTA EXHAUSTED. Marking as daily limited.")
            if api_key:
                self.tracker.mark_exhausted(api_key)
        else:
            logger.warning(f"Gemini API key {api_key[:6]}... RATE LIMITED (429). Pausing for a minute.")
            if api_key:
                self.tracker.mark_rate_limited(api_key)

    def _get_model(self, system_instruction: str = None, generation_config: Any = None, tools: Any = None):
        """Finds an available key (respecting both daily and per-minute limits)
        and returns a configured model instance.

        Calls wait_for_slot which will:
        - Return immediately if a key has a free per-minute slot.
        - Automatically rotate to another key if the current one is minute-limited.
        - Sleep until the next slot opens if ALL keys are at their minute limit.
        - Raise ValueError if all keys are daily-exhausted.
        """
        # Dynamically reload keys from environment file
        current_keys = config.get_gemini_keys()

        # Blocks until a key is available (rotates or waits as needed)
        api_key = self.tracker.wait_for_slot(current_keys)

        # Gemini SDK raises ValueError for empty-string system_instruction; use None instead.
        if not system_instruction:
            system_instruction = None

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=system_instruction,
            generation_config=generation_config,
            tools=tools
        )
        return api_key, model

    def generate(self, prompt: str, system_instruction: str = None) -> str:
        current_keys = config.get_gemini_keys()
        max_attempts = len(current_keys)
        last_error = None

        caller = system_instruction[:50].strip() if system_instruction else "generate"
        log_llm_start(caller, "generate")
        t0 = time.monotonic()

        for attempt in range(max_attempts):
            api_key = None
            try:
                api_key, model = self._get_model(system_instruction=system_instruction)
                response = model.generate_content(prompt, request_options={"timeout": 120})

                # Increment usage on success
                self.tracker.increment_usage(api_key)
                log_llm_done(caller, "generate", elapsed=time.monotonic() - t0)
                return response.text
            except Exception as e:
                last_error = e
                # Check for rate limit error (429)
                if "429" in str(e) or "resource_exhausted" in str(e).lower():
                    self._handle_limit_error(str(e), api_key)
                    continue
                elif _is_timeout(e):
                    logger.warning("Gemini generate timed out. Retrying...")
                    continue
                elif _is_server_error(e):
                    wait = 5 * (attempt + 1)
                    logger.warning(f"Gemini generate server error (5xx). Retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                else:
                    logger.error(f"Error generating content with Gemini: {e}")
                    raise e

        raise last_error

    def generate_structured(self, prompt: str, response_model: Type[BaseModel]) -> BaseModel:
        """Generate structured response using JSON mode with key rotation."""
        max_retries = 3
        last_error = None

        caller = response_model.__name__
        log_llm_start(caller, "generate_structured")
        t0 = time.monotonic()

        schema_example = response_model.model_json_schema()
        enhanced_prompt = f"""{prompt}

IMPORTANT: Return ONLY a valid JSON object that matches this structure:
{json.dumps(schema_example, indent=2)}

Do not include any markdown formatting, code blocks, or explanations. Return only the raw JSON object."""

        for attempt in range(max_retries):
            api_key = None
            try:
                generation_config = GenerationConfig(response_mime_type="application/json")
                api_key, model = self._get_model(generation_config=generation_config)

                response = model.generate_content(enhanced_prompt, request_options={"timeout": 120})
                response_text = response.text.strip()
                response_text = self._clean_json_response(response_text)

                json_response = json.loads(response_text)
                validated = response_model.model_validate(json_response)

                self.tracker.increment_usage(api_key)
                logger.info(f"Successfully generated structured content on attempt {attempt + 1}")
                log_llm_done(caller, "generate_structured", elapsed=time.monotonic() - t0)
                return validated

            except (json.JSONDecodeError, Exception) as e:
                last_error = e
                # Handle rate limits
                if "429" in str(e) or "resource_exhausted" in str(e).lower():
                    self._handle_limit_error(str(e), api_key)
                    continue
                elif _is_timeout(e):
                    logger.warning("Gemini generate_structured timed out. Retrying...")
                    continue
                elif _is_server_error(e):
                    wait = 5 * (attempt + 1)
                    logger.warning(f"Gemini generate_structured server error (5xx). Retrying in {wait}s...")
                    time.sleep(wait)
                    continue

                logger.warning(f"Error in structured generation attempt {attempt + 1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    continue

        raise last_error

    def generate_with_tools(
        self,
        system_instruction: str,
        history: List[Dict[str, Any]],
        tool_declarations: List[Any],
        caller: str = "Coder",
    ) -> Dict[str, Any]:
        """Generate a response with tools, using REST API directly to avoid SDK serialization bugs."""
        current_keys = config.get_gemini_keys()
        max_attempts = len(current_keys)
        last_error = None

        log_llm_start(caller, "generate_with_tools")
        t0 = time.monotonic()

        for attempt in range(max_attempts):
            api_key = self.tracker.wait_for_slot(current_keys)
            
            payload = {}
            if system_instruction:
                 payload["systemInstruction"] = {
                     "role": "system",
                     "parts": [{"text": system_instruction}]
                 }
                 
            if tool_declarations:
                 from google.protobuf.json_format import MessageToDict
                 dict_decls = []
                 for t in tool_declarations:
                     if hasattr(t, "_pb"):
                         dict_decls.append(MessageToDict(t._pb))
                     elif isinstance(t, dict):
                         dict_decls.append(t)
                     elif hasattr(t, "to_dict"):
                         dict_decls.append(type(t).to_dict(t))
                     else:
                         dict_decls.append(t)
                 payload["tools"] = [{"functionDeclarations": dict_decls}]
                 
            payload["contents"] = self._build_rest_contents(history)
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={api_key}"

            try:
                # We do requests.post instead of SDK call
                response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=120)
                
                if response.status_code == 429 or response.status_code == 403: # 403 is sometimes used for exhaustion
                    self._handle_limit_error(response.text or "Rate limit/Quota exceeded", api_key)
                    continue

                if response.status_code >= 500:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"Gemini API server error {response.status_code}. Retrying in {wait}s...")
                    time.sleep(wait)
                    continue

                if not response.ok:
                    logger.error(f"Gemini API Error {response.status_code}: {response.text}")
                response.raise_for_status()
                response_json = response.json()

                self.tracker.increment_usage(api_key)
                result = self._parse_rest_tool_response(response_json)
                tool_calls = result.get("tool_calls")
                suffix = f"  → tool_calls: {[tc['name'] for tc in tool_calls]}" if tool_calls else ""
                log_llm_done(caller, "generate_with_tools", elapsed=time.monotonic() - t0)
                if suffix:
                    from core.log import console
                    console.print(f"  [dim]{suffix.strip()}[/dim]")
                return result

            except Exception as e:
                last_error = e
                # Check for rate limit error (429) via general exception just in case
                if "429" in str(e) or "resource_exhausted" in str(e).lower():
                    self._handle_limit_error(str(e), api_key)
                    continue
                elif _is_timeout(e):
                    logger.warning("Gemini generate_with_tools timed out. Retrying...")
                    continue
                elif _is_server_error(e):
                    wait = 5 * (attempt + 1)
                    logger.warning(f"Gemini generate_with_tools server error (5xx). Retrying in {wait}s...")
                    time.sleep(wait)
                    continue

                logger.error(f"Error in generate_with_tools: {e}", exc_info=True)
                raise

        raise last_error

    def _build_rest_contents(self, history: List[Dict[str, Any]]) -> list:
        contents = []
        for entry in history:
            role = entry.get("role", "user")
            parts = entry.get("parts", [])
            
            built_parts = []
            for part in parts:
                if isinstance(part, str):
                    built_parts.append({"text": part})
                elif isinstance(part, dict) and part.get("thought"):
                    built_parts.append({"text": part.get("text", ""), "thought": True})
                elif isinstance(part, dict) and "function_response" in part:
                    fr = part["function_response"]
                    fr_dict = {
                        "name": fr["name"],
                        "response": fr["response"]
                    }
                    if "id" in fr:
                        fr_dict["id"] = fr["id"]
                    built_parts.append({
                        "functionResponse": fr_dict
                    })
                elif isinstance(part, dict) and "function_call" in part:
                    # Echo back function call
                    fc = part["function_call"]
                    fc_part = {"functionCall": {"name": fc["name"], "args": fc.get("args", {})}}
                    if "id" in fc and fc["id"]:
                        fc_part["functionCall"]["id"] = fc["id"]
                    if "thought_signature" in part:
                        fc_part["thoughtSignature"] = part["thought_signature"]
                    elif "thoughtSignature" in part:
                        fc_part["thoughtSignature"] = part["thoughtSignature"]
                    built_parts.append(fc_part)
                elif isinstance(part, dict) and part.get("type") == "image_url":
                     url = part.get("image_url", {}).get("url", "")
                     if url.startswith("data:image/"):
                         mime_part, b64_part = url.split(";", 1)
                         mime_type = mime_part.replace("data:", "")
                         if b64_part.startswith("base64,"):
                             b64_data = b64_part.replace("base64,", "")
                             built_parts.append({"inlineData": {"mimeType": mime_type, "data": b64_data}})
                else:
                    built_parts.append({"text": str(part)})
            contents.append({"role": role, "parts": built_parts})
        return contents

    def _parse_rest_tool_response(self, response_json: Dict[str, Any]) -> Dict[str, Any]:
        text_parts = []
        tool_calls = []
        serializable_parts = []

        candidates = response_json.get("candidates", [])
        if not candidates:
            return {"text": "No response generated.", "tool_calls": None, "raw_parts": []}
            
        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        
        for part in parts:
            if part.get("thought"):
               serializable_parts.append({
                   "thought": True,
                   "text": part.get("text", "")
               })
            elif "functionCall" in part:
                 fc = part["functionCall"]
                 tc = {
                     "name": fc.get("name"),
                     "args": fc.get("args", {})
                 }
                 if "id" in fc:
                     tc["id"] = fc["id"]
                 tool_calls.append(tc)
                 
                 fc_out = {
                     "name": fc.get("name"),
                     "args": fc.get("args", {})
                 }
                 if "id" in fc:
                     fc_out["id"] = fc["id"]
                 
                 serializable_part = {
                     "function_call": fc_out
                 }
                 if "thoughtSignature" in part:
                     serializable_part["thought_signature"] = part["thoughtSignature"]
                 elif "thought_signature" in part:
                     serializable_part["thought_signature"] = part["thought_signature"]
                 serializable_parts.append(serializable_part)
            elif "text" in part:
                 text_parts.append(part["text"])
                 serializable_parts.append(part["text"])

        return {
            "text": "\n".join(text_parts) if text_parts else None,
            "tool_calls": tool_calls if tool_calls else None,
            "raw_parts": serializable_parts,
        }



    def _build_contents(self, history: List[Dict[str, Any]]) -> list:
        """Convert our history dict format into Gemini Content protos."""
        contents = []
        for entry in history:
            role = entry.get("role", "user")
            parts = entry.get("parts", [])
            
            built_parts = []
            for part in parts:
                if isinstance(part, str):
                    built_parts.append(genai.protos.Part(text=part))
                elif isinstance(part, dict) and part.get("thought"):
                    # Thought-only part from a thinking model — must be echoed back
                    built_parts.append(genai.protos.Part(
                        text=part.get("text", ""),
                        thought=True,
                    ))
                elif isinstance(part, dict) and "function_response" in part:
                    # This is a function result being fed back
                    fr = part["function_response"]
                    built_parts.append(genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fr["name"],
                            response=fr["response"],
                        )
                    ))
                elif isinstance(part, dict) and "function_call" in part:
                    # Echo back the function call the model made (for multi-turn).
                    # CRITICAL: restore thought_signature if it was preserved — Gemini
                    # thinking models require this field to be present on function_call
                    # parts when continuing a conversation, or they return 400.
                    fc = part["function_call"]
                    proto_part = genai.protos.Part(
                        function_call=genai.protos.FunctionCall(
                            name=fc["name"],
                            args=fc["args"],
                        )
                    )
                    if part.get("thought_signature"):
                        try:
                            proto_part.thought_signature = base64.b64decode(
                                part["thought_signature"]
                            )
                        except Exception as e:
                            logger.warning("Could not restore thought_signature: %s", e)
                    built_parts.append(proto_part)
                elif isinstance(part, dict) and part.get("type") == "image_url":
                    # Handle OpenAI-style vision payload
                    url = part.get("image_url", {}).get("url", "")
                    if url.startswith("data:image/"):
                        # Extract mime type and base64 data
                        # Format: data:image/png;base64,iVBORw0KGgo...
                        mime_part, b64_part = url.split(";", 1)
                        mime_type = mime_part.replace("data:", "")
                        if b64_part.startswith("base64,"):
                            b64_data = b64_part.replace("base64,", "")
                            try:
                                raw_bytes = base64.b64decode(b64_data)
                                built_parts.append(genai.protos.Part(
                                    inline_data=genai.protos.Blob(
                                        mime_type=mime_type,
                                        data=raw_bytes
                                    )
                                ))
                            except Exception as e:
                                logger.error(f"Failed to decode base64 image: {e}")
                elif hasattr(part, "function_call") or hasattr(part, "text") or hasattr(part, "executable_code") or hasattr(part, "thought"):
                    # Already a proto part object, pass through
                    built_parts.append(part)
                else:
                    # Fallback: stringify
                    built_parts.append(genai.protos.Part(text=str(part)))

            contents.append(genai.protos.Content(
                role=role,
                parts=built_parts,
            ))
        return contents

    def _parse_tool_response(self, response) -> Dict[str, Any]:
        """Extract text and/or function calls from a Gemini response.

        raw_parts is returned as a list of plain serializable dicts (NOT proto
        objects) so that tool_loop_history can be checkpointed by LangGraph
        without hitting ormsgpack's "Type is not msgpack serializable: Part".
        _build_contents handles plain dicts and reconstructs protos from them.

        Critically, for Gemini thinking models:
        - Thought parts (part.thought=True) are preserved as {"thought": True, "text": ...}
        - thought_signature bytes on function_call parts are preserved as base64
          strings so they survive msgpack serialization and can be restored in
          _build_contents. Without this, the API returns 400 on the next turn.
        """
        text_parts = []
        tool_calls = []
        serializable_parts = []  # plain dicts — safe for LangGraph checkpointing

        # The response may have multiple candidates; we use the first
        if not response.candidates:
            return {"text": "No response generated.", "tool_calls": None, "raw_parts": []}

        candidate = response.candidates[0]

        for part in candidate.content.parts:
            # ---------- thought parts (thinking model) ----------
            if getattr(part, "thought", False):
                # Must be echoed back in multi-turn; not shown to user.
                serializable_parts.append({
                    "thought": True,
                    "text": getattr(part, "text", ""),
                })
                continue

            # ---------- function call parts ----------
            if hasattr(part, "function_call") and part.function_call.name:
                args = {}
                if part.function_call.args:
                    for key, value in part.function_call.args.items():
                        args[key] = _proto_value_to_python(value)
                tool_calls.append({
                    "name": part.function_call.name,
                    "args": args,
                })
                # Serialise as plain dict; preserve thought_signature (bytes) as
                # base64 so it survives msgpack and can be restored by _build_contents.
                serializable_part: Dict[str, Any] = {
                    "function_call": {
                        "name": part.function_call.name,
                        "args": args,
                    }
                }
                thought_sig = getattr(part, "thought_signature", None)
                if thought_sig:
                    serializable_part["thought_signature"] = base64.b64encode(
                        bytes(thought_sig)
                    ).decode("ascii")
                serializable_parts.append(serializable_part)

            # ---------- text parts ----------
            elif hasattr(part, "text") and part.text:
                text_parts.append(part.text)
                serializable_parts.append(part.text)  # plain str — always serializable

        return {
            "text": "\n".join(text_parts) if text_parts else None,
            "tool_calls": tool_calls if tool_calls else None,
            "raw_parts": serializable_parts,
        }


    def _clean_json_response(self, text: str) -> str:
        """Clean JSON response text to handle common formatting issues."""
        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines if they're markdown fences
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
        
        # Strip whitespace
        text = text.strip()
        
        return text


def _proto_value_to_python(value) -> Any:
    """Convert a protobuf Value to a native Python type.
    
    Gemini function_call args come as google.protobuf.struct_pb2.Value objects.
    This handles all Value kinds: string, number, bool, null, list, struct.
    """
    # If it's already a plain Python type (str, int, dict, etc.), return as-is.
    # This happens when the SDK auto-converts for us in newer versions.
    if isinstance(value, (str, int, float, bool, type(None), list, dict)):
        return value
    
    # Handle protobuf Value types
    kind = value.WhichOneof("kind") if hasattr(value, "WhichOneof") else None
    
    if kind == "string_value":
        return value.string_value
    elif kind == "number_value":
        return value.number_value
    elif kind == "bool_value":
        return value.bool_value
    elif kind == "null_value":
        return None
    elif kind == "list_value":
        return [_proto_value_to_python(v) for v in value.list_value.values]
    elif kind == "struct_value":
        return {k: _proto_value_to_python(v) for k, v in value.struct_value.fields.items()}
    else:
        # Fallback — try to extract via string conversion
        return str(value)


class LLMFactory:
    """Factory for creating LLM provider instances."""

    @staticmethod
    def get_provider(model_name: str = None) -> LLMProvider:
        provider_name = config.LLM_PROVIDER.lower()

        if provider_name == "gemini":
            return GeminiProvider(model_name=model_name)
        elif provider_name == "openai":
            # Placeholder for OpenAI implementation
            raise NotImplementedError("OpenAI provider is not yet implemented.")
        else:
            raise ValueError(f"Unsupported LLM provider: {provider_name}")
