"""
AWS Bedrock client for Llama 3 70B Instruct.
Handles communication with the AI model for conversation generation.
All boto3 calls use asyncio.to_thread to avoid blocking the event loop.
"""

import asyncio
import json
from typing import Optional, AsyncGenerator
import boto3
import structlog

from config import settings

logger = structlog.get_logger()


class BedrockClient:
    """
    Client for AWS Bedrock with Meta Llama 3 70B Instruct.
    Provides non-blocking response generation.
    """

    def __init__(self):
        self.model_id = settings.bedrock_model_id
        self.region = settings.aws_region
        self.max_tokens = settings.bedrock_max_tokens
        self.temperature = settings.bedrock_temperature
        self.top_p = settings.bedrock_top_p
        self.runtime_client = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the Bedrock runtime client."""
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
        Generate a response from Llama 3 70B (non-blocking).

        Args:
            prompt: User message / conversation input
            system_prompt: System instruction for the model
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Top-p nucleus sampling

        Returns:
            Generated response text
        """
        if not self._initialized:
            raise RuntimeError("Bedrock client not initialized")

        formatted_prompt = self._format_llama_prompt(prompt, system_prompt)

        body = json.dumps({
            "prompt": formatted_prompt,
            "max_gen_len": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "top_p": top_p if top_p is not None else self.top_p,
        })

        try:
            # Run blocking boto3 call in thread pool
            def _invoke():
                return self.runtime_client.invoke_model(
                    modelId=self.model_id,
                    body=body,
                    contentType="application/json",
                    accept="application/json"
                )

            response = await asyncio.to_thread(_invoke)
            response_body = json.loads(response["body"].read())
            generated_text = response_body.get("generation", "")

            # Clean response — remove any trailing special tokens
            generated_text = generated_text.strip()
            if "<|eot_id|>" in generated_text:
                generated_text = generated_text.split("<|eot_id|>")[0].strip()

            logger.info(
                "Bedrock response generated",
                prompt_length=len(prompt),
                response_length=len(generated_text)
            )

            return generated_text

        except Exception as e:
            logger.error("Error generating Bedrock response", error=str(e))
            return "I apologize, but I'm having trouble responding right now. Please try again."

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response from Llama 3 70B.
        Yields text chunks as they are generated.
        """
        if not self._initialized:
            raise RuntimeError("Bedrock client not initialized")

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

            response = await asyncio.to_thread(_invoke_stream)

            stream = response.get("body")
            if stream:
                for event in stream:
                    chunk = event.get("chunk")
                    if chunk:
                        data = json.loads(chunk.get("bytes", b"{}").decode())
                        text = data.get("generation", "")
                        if text:
                            yield text

        except Exception as e:
            logger.error("Error in streaming response", error=str(e))
            yield "I apologize, but I'm having trouble responding right now."

    def _format_llama_prompt(
        self,
        user_message: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Format the prompt for Llama 3 Instruct model.

        Llama 3 uses:
        <|begin_of_text|><|start_header_id|>system<|end_header_id|>
        {system_message}<|eot_id|>
        <|start_header_id|>user<|end_header_id|>
        {user_message}<|eot_id|>
        <|start_header_id|>assistant<|end_header_id|>
        """
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
        """Check if Bedrock is accessible."""
        try:
            response = await self.generate_response(
                "Say 'OK' in one word.",
                max_tokens=10,
                temperature=0.0
            )
            return len(response) > 0
        except Exception:
            return False
