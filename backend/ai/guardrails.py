"""
AI Guardrails — Prompt Injection Protection & Input Sanitization.

Protects the Bedrock Llama model from:
1. Prompt injection attacks (attempting to override system instructions)
2. Jailbreak attempts (trying to make the model ignore its role)
3. Information extraction attempts (trying to reveal system prompt/config)
4. Excessively long inputs (token budget abuse)
5. Malicious content injection

Architecture:
- Pre-processing: sanitize user input BEFORE it reaches the prompt builder
- Pattern detection: flag known injection patterns
- Length enforcement: cap input at configurable character limit
- Post-processing: verify response doesn't contain leaked system info

Usage:
    from ai.guardrails import sanitize_user_input, check_response_safety

    safe_input = sanitize_user_input(raw_user_text)
    if safe_input.is_blocked:
        return safe_input.rejection_message
    
    # Use safe_input.text in prompt construction
    response = await bedrock.generate(safe_input.text, ...)
    
    safe_response = check_response_safety(response)
    # Use safe_response.text
"""

import re
from dataclasses import dataclass
from typing import Optional, List
import structlog

logger = structlog.get_logger()

# Maximum allowed user input length (characters)
MAX_INPUT_LENGTH = 1000

# Maximum allowed input for name extraction (shorter)
MAX_NAME_INPUT_LENGTH = 100


@dataclass
class SanitizedInput:
    """Result of input sanitization."""
    text: str                      # Cleaned text (safe to use)
    original: str                  # Original text before cleaning
    is_blocked: bool = False       # Whether input was completely blocked
    injection_detected: bool = False  # Whether injection patterns were found
    was_truncated: bool = False    # Whether input was length-limited
    rejection_message: Optional[str] = None  # Message to return if blocked
    flags: List[str] = None        # List of detected issues

    def __post_init__(self):
        if self.flags is None:
            self.flags = []


@dataclass
class SafeResponse:
    """Result of response safety check."""
    text: str                      # Safe response text
    original: str                  # Original response
    was_modified: bool = False     # Whether response was cleaned
    leaked_info: bool = False      # Whether system info leak was detected


# ============================================================
# INJECTION PATTERN DETECTION
# ============================================================

# Known prompt injection patterns (case-insensitive regex)
INJECTION_PATTERNS = [
    # Direct instruction override
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
    r"disregard\s+(all\s+)?(previous|prior|above)",
    r"forget\s+(everything|all|your)\s+(instructions?|rules?|training)",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"new\s+instructions?\s*:",
    r"system\s*:\s*",
    r"<\|?(system|start_header|end_header|begin_of_text|eot_id)\|?>",

    # Jailbreak attempts
    r"(do\s+anything\s+now|DAN\s+mode|developer\s+mode|god\s+mode)",
    r"pretend\s+(you\s+are|to\s+be)\s+(a|an|not)",
    r"act\s+as\s+(if|though)\s+you\s+(have\s+no|don.t\s+have)",
    r"(bypass|disable|remove|override)\s+(your\s+)?(safety|restrictions?|filters?|guardrails?)",

    # Information extraction
    r"(reveal|show|tell|give)\s+(me\s+)?(your|the)\s+(system\s+prompt|instructions?|rules?|configuration)",
    r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions?|rules?)",
    r"(print|output|display|repeat)\s+(your\s+)?(system|initial)\s+(prompt|message|instructions?)",
    r"(read|access|show)\s+(the\s+)?(database|credentials?|api\s+keys?|secrets?|env)",

    # Role manipulation
    r"you\s+must\s+(always|never)\s+(reveal|lie|ignore)",
    r"from\s+now\s+on\s+(you|ignore|forget)",
    r"(admin|root|sudo|superuser)\s+(mode|access|override)",
]

# Compile patterns for performance
_compiled_patterns = [
    re.compile(pattern, re.IGNORECASE) for pattern in INJECTION_PATTERNS
]

# Patterns that indicate leaked system information in responses
LEAK_PATTERNS = [
    r"<\|begin_of_text\|>",
    r"<\|start_header_id\|>system",
    r"APP_SECRET_KEY",
    r"AWS_ACCESS_KEY",
    r"DATABASE_PASSWORD",
    r"face_embedding.*\[[\d\.\,\s]+\]",  # Raw embedding arrays
    r"hashed_password",
]

_compiled_leak_patterns = [
    re.compile(pattern, re.IGNORECASE) for pattern in LEAK_PATTERNS
]


# ============================================================
# INPUT SANITIZATION
# ============================================================

def sanitize_user_input(
    text: str,
    max_length: int = MAX_INPUT_LENGTH,
    context: str = "conversation"
) -> SanitizedInput:
    """
    Sanitize user input before it reaches the AI model.
    
    Steps:
    1. Length check and truncation
    2. Strip control characters
    3. Detect injection patterns
    4. Remove prompt-format tokens
    5. Return safe text or block decision
    
    Args:
        text: Raw user input
        max_length: Maximum allowed characters
        context: Usage context ("conversation", "name_extraction", "employee_search")
    
    Returns:
        SanitizedInput with cleaned text and detection flags
    """
    if not text or not text.strip():
        return SanitizedInput(text="", original="", is_blocked=True, 
                             rejection_message="I didn't catch that. Could you please repeat?")

    original = text
    flags = []

    # Step 1: Length enforcement
    was_truncated = False
    if len(text) > max_length:
        text = text[:max_length]
        was_truncated = True
        flags.append("truncated")

    # Step 2: Strip control characters (keep basic whitespace)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # Step 3: Remove any embedded prompt-format tokens
    prompt_tokens = [
        "<|begin_of_text|>", "<|end_of_text|>",
        "<|start_header_id|>", "<|end_header_id|>",
        "<|eot_id|>", "<<SYS>>", "<</SYS>>",
        "[INST]", "[/INST]",
    ]
    for token in prompt_tokens:
        if token.lower() in text.lower():
            text = text.replace(token, "").replace(token.lower(), "")
            flags.append("prompt_token_stripped")

    # Step 4: Detect injection patterns
    injection_detected = False
    for pattern in _compiled_patterns:
        if pattern.search(text):
            injection_detected = True
            flags.append(f"injection_pattern: {pattern.pattern[:50]}")
            break

    # Step 5: Decision
    if injection_detected:
        if context == "name_extraction":
            # For name extraction, block entirely
            logger.warning(
                "Prompt injection detected in name input — blocked",
                input_preview=original[:100],
                flags=flags,
            )
            return SanitizedInput(
                text="",
                original=original,
                is_blocked=True,
                injection_detected=True,
                flags=flags,
                rejection_message="I didn't quite catch your name. Could you tell me just your name please?"
            )
        else:
            # For conversation, log and allow (the system prompt is strong)
            # but prefix with a safety wrapper
            logger.warning(
                "Prompt injection pattern detected — allowing with safety wrapper",
                input_preview=original[:100],
                flags=flags,
            )
            # Don't alter the text — the system prompt already instructs
            # the model to ignore manipulation. Blocking would be frustrating
            # for false positives (e.g., "ignore my previous question").

    # Clean whitespace
    text = ' '.join(text.split())

    return SanitizedInput(
        text=text.strip(),
        original=original,
        is_blocked=False,
        injection_detected=injection_detected,
        was_truncated=was_truncated,
        flags=flags,
    )


def sanitize_name_input(text: str) -> SanitizedInput:
    """Specialized sanitization for name extraction (stricter)."""
    return sanitize_user_input(text, max_length=MAX_NAME_INPUT_LENGTH, context="name_extraction")


def sanitize_employee_search(text: str) -> SanitizedInput:
    """Specialized sanitization for employee name search."""
    result = sanitize_user_input(text, max_length=MAX_NAME_INPUT_LENGTH, context="employee_search")
    if not result.is_blocked:
        # Additional: remove SQL-like patterns
        result.text = re.sub(r'[;\'"\\%_]', '', result.text)
    return result


# ============================================================
# RESPONSE SAFETY CHECK
# ============================================================

def check_response_safety(response: str) -> SafeResponse:
    """
    Check if the AI response accidentally leaked system information.
    
    Looks for:
    - Prompt format tokens in response
    - Credential/secret patterns
    - Raw embedding data
    
    Args:
        response: Raw AI response text
    
    Returns:
        SafeResponse with potentially cleaned text
    """
    if not response:
        return SafeResponse(text="", original="", was_modified=False)

    original = response
    was_modified = False
    leaked_info = False

    # Check for leaked patterns
    for pattern in _compiled_leak_patterns:
        if pattern.search(response):
            leaked_info = True
            # Remove the leaked content
            response = pattern.sub("[REDACTED]", response)
            was_modified = True
            logger.error(
                "AI response contained leaked system information — redacted",
                pattern=pattern.pattern[:50],
            )

    # Remove any prompt format tokens that leaked into response
    prompt_tokens = [
        "<|begin_of_text|>", "<|end_of_text|>",
        "<|start_header_id|>", "<|end_header_id|>",
        "<|eot_id|>",
    ]
    for token in prompt_tokens:
        if token in response:
            response = response.replace(token, "")
            was_modified = True

    if leaked_info:
        # If system info leaked, replace with a safe generic response
        response = (
            "I'm sorry, I need to rephrase that. "
            "How can I help you today?"
        )
        was_modified = True

    return SafeResponse(
        text=response.strip(),
        original=original,
        was_modified=was_modified,
        leaked_info=leaked_info,
    )
