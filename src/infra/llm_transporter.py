import os
import re
import time
import certifi
from typing import Optional, Dict, Any, List, Final
from openai import OpenAI, RateLimitError, APITimeoutError, APIConnectionError, AuthenticationError, APIError
from src.config.settings import (
    LLM_CONFIG, 
    LLM_PRIORITY_ORDER, 
    LLM_RETRY_PARAMS
)
from src.lib.logger import setup_llm_logger
from src.lib.guard import INJECTION_PATTERNS as _INJECTION_PATTERNS

os.environ['SSL_CERT_FILE'] = certifi.where()
logger = setup_llm_logger(__name__)

class LlmTransporter:
    __REV: Final[str] = "Rev. 15"

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing LlmTransporter")

    def __assert_prompt_integrity(self, prompt: str) -> None:
        lower = prompt.lower()
        detected = [p for p in _INJECTION_PATTERNS if p.lower() in lower]
        if detected:
            logger.warning(f"[Guard] Prompt integrity violation before dispatch: {detected}")
            raise RuntimeError(f"Prompt integrity violation: {detected}")
        logger.info("[Audit] Prompt integrity OK")

    def request_intelligence(self, prompt: str) -> str:
        logger.info(f"[Acquisition] Dispatching intelligence request (Size: {len(prompt)})")
        self.__assert_prompt_integrity(prompt)

        last_exception = None

        for provider in LLM_PRIORITY_ORDER:
            config = LLM_CONFIG.get(provider)
            if not config or not config.get("api_key"):
                logger.warning(f"[Guard] Skipping {provider}: Configuration or API Key missing")
                continue

            logger.info(f"[Acquisition] Connecting to provider: {provider.upper()}")
            
            try:
                if provider == "claude":
                    from anthropic import (
                        Anthropic,
                        RateLimitError as ClaudeRateLimit,
                        APIConnectionError as ClaudeAPIConnectionError,
                        APIStatusError as ClaudeAPIStatusError,
                    )
                    client = Anthropic(api_key=config["api_key"])
                else:
                    client = OpenAI(
                        api_key=config["api_key"],
                        base_url=config.get("base_url")
                    )
            except Exception as e:
                logger.error(f"[Acquisition] Client initialization failed for {provider}: {e}")
                continue
            
            max_retries = LLM_RETRY_PARAMS.get("max_retries", 3)
            base_delay = LLM_RETRY_PARAMS.get("base_delay", 5.0)
            timeout = LLM_RETRY_PARAMS.get("timeout", 90.0)
            enable_dynamic = LLM_RETRY_PARAMS.get("enable_dynamic_wait", True)

            for attempt in range(max_retries + 1):
                try:
                    logger.debug(f"[Acquisition] Prompt (provider={provider.upper()}, chars={len(prompt)}, preview={prompt[:200]!r}...)")
                    _t0 = time.time()
                    if provider == "claude":
                        response = client.messages.create(
                            model=config["model"],
                            max_tokens=config.get("max_tokens", 4000),
                            messages=[{"role": "user", "content": prompt}]
                        )
                        content = response.content[0].text
                        self.__log_token_usage(provider, getattr(response, 'usage', None), is_claude=True, elapsed=round(time.time() - _t0, 2))
                    else:
                        response = client.chat.completions.create(
                            model=config["model"],
                            messages=[{"role": "user", "content": prompt}],
                            timeout=timeout
                        )
                        content = response.choices[0].message.content
                        self.__log_token_usage(provider, getattr(response, 'usage', None), is_claude=False, elapsed=round(time.time() - _t0, 2))

                    if not content:
                        raise ValueError("Empty response received")

                    logger.debug(f"[Parsing] Response (provider={provider.upper()}, chars={len(content)}, preview={content[:200]!r}...)")
                    logger.info(f"[Parsing] Intelligence received (Provider: {provider.upper()}, Length: {len(content)})")
                    return content

                except Exception as e:
                    if provider == "claude":
                        if isinstance(e, (ClaudeRateLimit, ClaudeAPIConnectionError, ClaudeAPIStatusError)):
                            if attempt < max_retries:
                                sleep_time = base_delay * (2 ** attempt)
                                logger.warning(f"[Acquisition] {provider.upper()} transient error: {e}")
                                logger.info(f"[Acquisition] Exponential backoff: {sleep_time:.2f}s (Attempt {attempt+1})")
                                time.sleep(sleep_time)
                            else:
                                logger.error(f"[Outcome] {provider.upper()} retry exhausted")
                                last_exception = e
                                break
                        else:
                            logger.error(f"[Outcome] {provider.upper()} critical error: {e}")
                            last_exception = e
                            break
                    
                    elif isinstance(e, (RateLimitError, APITimeoutError, APIConnectionError)):
                        if attempt < max_retries:
                            sleep_time = 0.0
                            is_dynamic = False
                            
                            if isinstance(e, RateLimitError) and enable_dynamic:
                                match = re.search(r"Please retry in (\d+(\.\d+)?)s", str(e))
                                if match:
                                    sleep_time = float(match.group(1)) + 1.0
                                    is_dynamic = True
                            
                            if not is_dynamic:
                                sleep_time = base_delay * (2 ** attempt)

                            logger.warning(f"[Acquisition] {provider.upper()} transient error: {e}")
                            logger.info(f"[Acquisition] {'Dynamic' if is_dynamic else 'Exponential'} wait: {sleep_time:.2f}s")
                            time.sleep(sleep_time)
                        else:
                            logger.error(f"[Outcome] {provider.upper()} retry exhausted")
                            last_exception = e
                            break
                    
                    elif isinstance(e, (AuthenticationError, APIError)):
                        logger.error(f"[Outcome] {provider.upper()} auth/api error: {e}")
                        last_exception = e
                        break
                    
                    else:
                        logger.error(f"[Outcome] {provider.upper()} unexpected failure: {e}")
                        last_exception = e
                        break

        error_msg = f"All AI providers failed. Final exception: {last_exception}"
        logger.error(f"[Outcome] CRITICAL_TRANSPORTER_FAILURE: {error_msg}")
        raise RuntimeError(error_msg)

    def __log_token_usage(self, provider: str, usage: Any, is_claude: bool, elapsed: float = 0.0) -> None:
        if usage is None:
            logger.warning(f"[Guard] Token usage unavailable for {provider.upper()}: usage object is None")
            return
        try:
            if is_claude:
                input_tokens = usage.input_tokens
                output_tokens = usage.output_tokens
            else:
                input_tokens = usage.prompt_tokens
                output_tokens = usage.completion_tokens
            ratio = round(output_tokens / input_tokens, 2) if input_tokens > 0 else 0.0
            logger.info(f"[Outcome] Token Usage: provider={provider.upper()}, input={input_tokens}, output={output_tokens}, ratio={ratio}, elapsed={elapsed}s")
        except AttributeError as e:
            logger.warning(f"[Guard] Token usage unavailable for {provider.upper()}: {e}")
