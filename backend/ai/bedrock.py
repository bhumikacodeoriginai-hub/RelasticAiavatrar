"""
AWS Bedrock client for Llama 3 70B Instruct.
Handles communication with the AI model for conversation generation.

Resilience patterns:
- Request timeout (configurable, default 30s)
- Circuit breaker (opens after 3 consecutive failures, recovers after 30s)
- Exponential backoff retry (3 attempts with 1s/2s/4s delays)
- Token tracking per request
- Graceful fallback message on all failure paths

All boto3 calls use asyncio.to_thread to avoid blocking the event loop.
"""

import asyncio
import json
import time
from typing import Optional, AsyncGenerator

import boto3
import structlog

from config import settings
from services.resilience import CircuitBreaker, with_retry, CircuitOpenError

logger = structlog.get_logger()

# Circuit breaker for Bedrock API
_bedrock_circuit = CircuitBreaker(
    name="bedrock",
    failure_threshold=3,
    recovery_timeout=30.0,
    success_threshold=2,
)

# Configurable timeout for Bedrock calls
BEDROCK_TIMEOUT_SECONDS = 30.0

# Fallback message when Bedrock is unavailable
FALLBACK_MESSAGE = (
    "I apologize, but I'm having a brief technical difficulty. "
    "Please try again in a moment, or let me know how else I can help."
)


class BedrockClient:
    """
    Client for AWS Bedrock with Meta Llama 3 70B Instruct.
    Provides non-blocking, resilient response generation with
    circuit breaker, retry, timeout, and token tracking.
    """

    def __init__(self):
        self.model_id = settings.bedrock_model_id
        self.region = settings.aws_region
        self.max_tokens = settings.bedrock_max_tokens
        self.temperature = settings.bedrock_temperature
        self.top_p = settings.bedrock_top_p
        self.runtime_client = None
        self._initialized = False

        # Token tracking
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_requests = 0
        self._total_errors = 0
        self._total_latency_ms = 0

    async def initialize(self) -> None:
        """Initialize the Bedrock runtime client (non-blocking)."""
        try:
            def _create_client():
                session = boto3.Session(
                    region_name=self.region,
                    aws_access_key_id=settings.aws_access_key_id,
                    aws_secret_access_key=settings.aws_secret_access_key
                )
                return session.client("bedrock-runtime")

            self.runtime_client = await asyncio.to_thread(_create_client)
            self._initialized = True
            logger.info(
                "Bedrock client initialized",
                model=self.model_id,
                region=self.region
            )
        except Exception as e:
            logger.error("Failed to initialize Bedrock client", error=str(e))
            raise

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None
    ) -> str:
        """
        Generate a response from Llama 3 70B with full resilience.
        
        Resilience chain:
        1. Check circuit breaker (fail fast if service is down)
        2. Retry with exponential backoff (up to 3 attempts)
        3. Timeout per attempt (30s default)
        4. Graceful fallback on all failure paths
        """
        if not self._initialized:
            logger.warning("Bedrock not initialized — returning fallback")
            return FALLBACK_MESSAGE

        try:
            return await self._generate_with_resilience(
                prompt, system_prompt, max_tokens, temperature, top_p
            )
        except CircuitOpenError:
            logger.warning("Bedrock circuit breaker OPEN — returning fallback")
            self._total_errors += 1
            return FALLBACK_MESSAGE
        except Exception as e:
            logger.error("Bedrock generation failed after all retries", error=str(e))
            self._total_errors += 1
            return FALLBACK_MESSAGE

    @with_retry(max_attempts=3, base_delay=1.0, max_delay=8.0, backoff_factor=2.0)
    async def _generate_with_resilience(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: Optional[int],
        temperature: Optional[float],
        top_p: Optional[float],
    ) -> str:
        """Internal: generate with circuit breaker and timeout."""
        async with _bedrock_circuit:
            return await self._invoke_model(
                prompt, system_prompt, max_tokens, temperature, top_p
            )

    async def _invoke_model(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: Optional[int],
        temperature: Optional[float],
        top_p: Optional[float],
    ) -> str:
        """Execute the actual Bedrock API call with timeout."""
        formatted_prompt = self._format_llama_prompt(prompt, system_prompt)
        tokens_requested = max_tokens or self.max_tokens

        body = json.dumps({
            "prompt": formatted_prompt,
            "max_gen_len": tokens_requested,
            "temperature": temperature if temperature is not None else self.temperature,
            "top_p": top_p if top_p is not None else self.top_p,
        })

        start_time = time.time()

        def _invoke():
            return self.runtime_client.invoke_model(
                modelId=self.model_id,
                body=body,
                contentType="application/json",
                accept="application/json"
            )

        # Execute with timeout
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(_invoke),
                timeout=BEDROCK_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            latency = int((time.time() - start_time) * 1000)
            logger.error("Bedrock request timed out", timeout_s=BEDROCK_TIMEOUT_SECONDS, latency_ms=latency)
            raise TimeoutError(f"Bedrock request timed out after {BEDROCK_TIMEOUT_SECONDS}s")

        # Parse response
        response_body = json.loads(response["body"].read())
        generated_text = response_body.get("generation", "")

        # Clean response
        generated_text = generated_text.strip()
        if "<|eot_id|>" in generated_text:
            generated_text = generated_text.split("<|eot_id|>")[0].strip()

        # Track metrics
        latency_ms = int((time.time() - start_time) * 1000)
        self._total_requests += 1
        self._total_latency_ms += latency_ms
        # Approximate token count (rough: 1 token ≈ 4 chars)
        self._total_input_tokens += len(formatted_prompt) // 4
        self._total_output_tokens += len(generated_text) // 4

        logger.info(
            "Bedrock response generated",
            prompt_length=len(prompt),
            response_length=len(generated_text),
            latency_ms=latency_ms,
            tokens_requested=tokens_requested,
        )

        return generated_text

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response from Llama 3 70B.
        Yields text chunks. No retry on streaming (partial data issue).
        """
        if not self._initialized:
            yield FALLBACK_MESSAGE
            return

        if not _bedrock_circuit.is_available:
            yield FALLBACK_MESSAGE
            return

        formatted_prompt = self._format_llama_prompt(prompt, system_prompt)

        body = json.dumps({
            "prompt": formatted_prompt,
            "max_gen_len": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "top_p": self.top_p,
        })

        try:
            def _invoke_stream():
                return self.runtime_client.invoke_model_with_response_stream(
                    modelId=self.model_id,
                    body=body,
                    contentType="application/json",
                    accept="application/json"
                )

            response = await asyncio.wait_for(
                asyncio.to_thread(_invoke_stream),
                timeout=BEDROCK_TIMEOUT_SECONDS
            )

            stream = response.get("body")
            if stream:
                for event in stream:
                    chunk = event.get("chunk")
                    if chunk:
                        data = json.loads(chunk.get("bytes", b"{}").decode())
                        text = data.get("generation", "")
                        if text:
                            yield text

            _bedrock_circuit.record_success()

        except Exception as e:
            _bedrock_circuit.record_failure()
            logger.error("Error in streaming response", error=str(e))
            yield FALLBACK_MESSAGE

    def _format_llama_prompt(
        self,
        user_message: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """Format the prompt for Llama 3 Instruct model."""
        parts = ["<|begin_of_text|>"]

        if system_prompt:
            parts.append(
                f"<|start_header_id|>system<|end_header_id|>\n\n"
                f"{system_prompt}<|eot_id|>"
            )

        parts.append(
            f"<|start_header_id|>user<|end_header_id|>\n\n"
            f"{user_message}<|eot_id|>"
        )

        parts.append(
            "<|start_header_id|>assistant<|end_header_id|>\n\n"
        )

        return "".join(parts)

    async def health_check(self) -> bool:
        """Check if Bedrock is accessible and circuit is closed."""
        if not self._initialized:
            return False
        if not _bedrock_circuit.is_available:
            return False
        try:
            response = await asyncio.wait_for(
                self._invoke_model("Say OK", None, 5, 0.0, None),
                timeout=10.0
            )
            return len(response) > 0
        except Exception:
            return False

    def get_metrics(self) -> dict:
        """Get usage metrics for monitoring/dashboards."""
        avg_latency = (
            self._total_latency_ms / self._total_requests
            if self._total_requests > 0 else 0
        )
        return {
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "average_latency_ms": int(avg_latency),
            "circuit_state": _bedrock_circuit.state.value,
        }
