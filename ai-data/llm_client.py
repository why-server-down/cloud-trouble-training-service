"""
LLM Client Wrapper
Provides a unified interface for OpenAI API calls with error handling and retry logic
"""

import time
from typing import Optional, Dict, List
from dataclasses import dataclass
import openai
from openai import OpenAI, APIError, RateLimitError, APIConnectionError

from config import config


@dataclass
class LLMResponse:
    """LLM response with metadata"""
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    finish_reason: str
    response_time: float


class LLMClientError(Exception):
    """Base exception for LLM client errors"""
    pass


class LLMClient:
    """
    LLM Client wrapper for OpenAI API
    Includes retry logic, error handling, and response formatting
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize LLM client
        
        Args:
            api_key: OpenAI API key (defaults to config)
            model: Model name (defaults to config)
            temperature: Temperature (defaults to config)
            max_tokens: Max tokens (defaults to config)
            timeout: Timeout in seconds (defaults to config)
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds
        """
        self.api_key = api_key or config.OPENAI_API_KEY
        self.model = model or config.OPENAI_MODEL
        self.temperature = temperature or config.OPENAI_TEMPERATURE
        self.max_tokens = max_tokens or config.OPENAI_MAX_TOKENS
        self.timeout = timeout or config.OPENAI_TIMEOUT
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            raise LLMClientError("OpenAI API key not configured")
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key)
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """
        Generate response from LLM
        
        Args:
            prompt: User prompt
            system_prompt: System prompt (optional)
            temperature: Override temperature
            max_tokens: Override max tokens
        
        Returns:
            LLMResponse with content and metadata
        
        Raises:
            LLMClientError: If generation fails after retries
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        # Use provided values or defaults
        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens
        
        # Retry logic
        last_error = None
        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temp,
                    max_tokens=tokens,
                    timeout=self.timeout
                )
                
                response_time = time.time() - start_time
                
                return LLMResponse(
                    content=response.choices[0].message.content,
                    model=response.model,
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens,
                    finish_reason=response.choices[0].finish_reason,
                    response_time=response_time
                )
            
            except RateLimitError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    print(f"Rate limit hit, retrying in {wait_time}s... (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    raise LLMClientError(f"Rate limit exceeded after {self.max_retries} retries: {str(e)}")
            
            except APIConnectionError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    print(f"Connection error, retrying in {wait_time}s... (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    raise LLMClientError(f"Connection failed after {self.max_retries} retries: {str(e)}")
            
            except APIError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay
                    print(f"API error, retrying in {wait_time}s... (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    raise LLMClientError(f"API error after {self.max_retries} retries: {str(e)}")
            
            except Exception as e:
                raise LLMClientError(f"Unexpected error: {str(e)}")
        
        # Should not reach here, but just in case
        raise LLMClientError(f"Failed after {self.max_retries} retries: {str(last_error)}")
    
    def test_connection(self) -> bool:
        """
        Test API connectivity
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.generate(
                prompt="Hello, this is a test.",
                max_tokens=10
            )
            return True
        except Exception as e:
            print(f"Connection test failed: {str(e)}")
            return False
    
    def get_stats(self) -> Dict:
        """Get client statistics"""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay
        }


def main():
    """Test LLM client"""
    print("="*80)
    print("LLM Client Test")
    print("="*80)
    
    try:
        # Initialize client
        print("\n1. Initializing LLM client...")
        client = LLMClient()
        print("   ✓ Client initialized")
        
        # Display stats
        print("\n2. Client configuration:")
        stats = client.get_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        # Test connection
        print("\n3. Testing API connection...")
        if client.test_connection():
            print("   ✓ Connection successful")
        else:
            print("   ✗ Connection failed")
            return
        
        # Test generation
        print("\n4. Testing text generation...")
        response = client.generate(
            prompt="Explain what Kubernetes is in one sentence.",
            max_tokens=50
        )
        
        print(f"   ✓ Response generated")
        print(f"   Model: {response.model}")
        print(f"   Tokens: {response.total_tokens} (prompt: {response.prompt_tokens}, completion: {response.completion_tokens})")
        print(f"   Response time: {response.response_time:.2f}s")
        print(f"   Content: {response.content}")
        
        print("\n" + "="*80)
        print("✓ ALL TESTS PASSED")
        print("="*80)
        
    except LLMClientError as e:
        print(f"\n✗ LLM Client Error: {str(e)}")
    except Exception as e:
        print(f"\n✗ Unexpected Error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
