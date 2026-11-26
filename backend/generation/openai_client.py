"""
Cognifin - OpenAI Client
=============================
Thin wrapper around the OpenAI API for generating grounded answers.

This module handles:
- Loading API key and model name from environment
- Sending chat completion requests to OpenAI
- Error handling (auth, rate-limit, timeout)

Phase: 2 (Generation Layer)
"""


# OpenAI SDK (v1+)
from openai import APIError, AuthenticationError, OpenAI, RateLimitError

from config import settings

# =============================================================================
# OPENAI CLIENT WRAPPER
# =============================================================================

class OpenAIClient:
    """
    Wrapper around the OpenAI API for generating answers.
    
    Why a wrapper?
    - Centralizes API key management
    - Handles errors in one place
    - Makes it easy to swap models later
    - Keeps main.py clean
    
    Usage:
        client = OpenAIClient()
        answer = client.generate("You are a helpful assistant.", "What is 2+2?")
    """
    
    def __init__(self):
        """
        Initialize the OpenAI client.
        
        Reads OPENAI_API_KEY and OPENAI_MODEL from environment.
        Does NOT crash if key is missing — instead, sets a flag so the
        /chat endpoint can return a helpful error.
        """
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_MODEL
        
        # Check if API key is configured
        self.is_configured = bool(self.api_key and self.api_key != "your-api-key-here")
        
        if self.is_configured:
            # Initialize the OpenAI client
            self.client = OpenAI(api_key=self.api_key, base_url=settings.OPENAI_BASE_URL or None)
            print(f"🔑 OpenAI client initialized (model: {self.model})")
        else:
            self.client = None
            print("⚠️  OpenAI API key not configured.")
            print("   The /chat endpoint will not work until you set OPENAI_API_KEY in .env")
            print("   The /retrieve and /health endpoints will continue to work normally.")
    
    def generate(self, system_prompt: str, user_message: str) -> str:
        """
        Generate a response using OpenAI's Chat Completion API.
        
        How it works:
        1. Send a system prompt (with grounding rules + context)
        2. Send the user's question
        3. Get back the model's response
        
        We use temperature=0 for deterministic, grounded answers.
        This minimizes creativity/hallucination — the model sticks
        closely to the provided context.
        
        Args:
            system_prompt: The full system prompt (includes context + grounding rules)
            user_message: The user's question
            
        Returns:
            The model's response text
            
        Raises:
            ValueError: If API key is not configured
            RuntimeError: If API call fails
        """
        # Guard: Check if client is configured
        if not self.is_configured or self.client is None:
            raise ValueError(
                "OpenAI API key is not configured. "
                "Please set OPENAI_API_KEY in your .env file and restart the server."
            )
        
        try:
            # Make the API call
            # temperature=0 → deterministic output (no creativity)
            # This is crucial for grounded answers
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0,       # Deterministic — no hallucination
                max_tokens=1000,     # Balanced: structured output without excess latency
            )
            
            # Extract the response text
            answer = response.choices[0].message.content.strip()
            return answer
            
        except Exception as e:
            raise _as_runtime_error(e) from e

    def generate_stream(self, system_prompt: str, user_message: str):
        """Like generate(), but yields the answer text as the model produces it."""
        if not self.is_configured or self.client is None:
            raise ValueError(
                "OpenAI API key is not configured. "
                "Please set OPENAI_API_KEY in your .env file and restart the server."
            )
        stream = None
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0,
                max_tokens=1000,
                stream=True,
            )
            for chunk in stream:
                text = chunk.choices[0].delta.content if chunk.choices else None
                if text:
                    yield text
        except Exception as e:
            raise _as_runtime_error(e) from e
        finally:
            # A closed tab closes this generator: stop the model generating (and billing).
            getattr(stream, "close", lambda: None)()


def _as_runtime_error(e: Exception) -> RuntimeError:
    """The one place OpenAI failures become user-facing messages."""
    if isinstance(e, AuthenticationError):
        return RuntimeError("Invalid OpenAI API key. Please check OPENAI_API_KEY in your .env file.")
    if isinstance(e, RateLimitError):
        return RuntimeError("OpenAI API rate limit exceeded. Please wait a moment and try again.")
    if isinstance(e, APIError):
        return RuntimeError(f"OpenAI API error: {str(e)}")
    return RuntimeError(f"Unexpected error calling OpenAI: {str(e)}")
