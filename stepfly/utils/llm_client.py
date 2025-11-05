import os
from typing import List, Dict, Any, Optional, Tuple
from openai import OpenAI
from stepfly.utils.config_loader import config

class LLMClient:
    def __init__(self, 
                 model: Optional[str] = None, 
                 api_base: Optional[str] = None,
                 api_key: Optional[str] = None):
        """
        Initialize LLM client for OpenAI API
        
        Parameters:
            model: Model name to use (overrides config)
            api_base: Base URL for OpenAI API (overrides config)
            api_key: API key for OpenAI API (overrides config)
        """
        # Set model from parameter or config
        self.model = model or config.get("llm.model", "gpt-4o-mini")
        
        # Set API base and key (priority: parameter > env var > config)
        self.api_base = api_base or os.environ.get("API_BASE") or config.get("llm.api_base", "https://api.openai.com/v1")
        self.api_key = api_key or os.environ.get("API_KEY") or config.get("llm.api_key")
        
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Please set it in config or pass as parameter.")
        
        # Initialize OpenAI client
        self._openai_client = OpenAI(
            base_url=self.api_base,
            api_key=self.api_key
        )
    
    def _extract_token_usage(self, response: Any) -> Dict[str, int]:
        """
        Extract token usage information from response
        
        Returns:
            Dictionary with input_tokens, output_tokens, total_tokens
        """
        usage_info = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }
        
        if hasattr(response, 'usage') and response.usage:
            usage = response.usage
            if hasattr(usage, 'prompt_tokens'):
                usage_info["input_tokens"] = usage.prompt_tokens
            if hasattr(usage, 'completion_tokens'):
                usage_info["output_tokens"] = usage.completion_tokens
            if hasattr(usage, 'total_tokens'):
                usage_info["total_tokens"] = usage.total_tokens
            else:
                # Calculate total if not provided
                usage_info["total_tokens"] = usage_info["input_tokens"] + usage_info["output_tokens"]
            
        return usage_info
    
    def get_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0,
        max_tokens: int = 4096,
        top_p: float = 0.95,
        stream: bool = False,
        json_response: bool = False
    ) -> Any:
        """
        Get completion content using OpenAI API
        
        Parameters:
            messages: List of message dictionaries
            temperature: Sampling temperature
            max_tokens: Maximum number of tokens to generate
            top_p: Top-p sampling parameter
            stream: Whether to stream the response
            json_response: Whether to request JSON format response
            
        Returns:
            Completion object or generator for streaming
        """
        # Prepare common parameters
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": stream
        }
        
        # Add response format if JSON is requested
        if json_response:
            params["response_format"] = {"type": "json_object"}
        
        # Add stream_options for token usage tracking when streaming
        if stream:
            params["stream_options"] = {"include_usage": True}
        
        return self._openai_client.chat.completions.create(**params)
    
    def stream_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0,
        max_tokens: int = 4096,
        top_p: float = 0.95,
        callback: Optional[callable] = None,
        json_response: bool = False
    ) -> Tuple[str, Dict[str, int]]:
        """
        Stream completion content from OpenAI API, calling the callback for each chunk
        
        Parameters:
            messages: List of message dictionaries
            temperature: Sampling temperature
            max_tokens: Maximum number of tokens to generate
            top_p: Top-p sampling parameter
            callback: Function to call for each chunk
            json_response: Whether to request JSON format response
            
        Returns:
            Tuple of (full generated text, token usage info)
        """
        # Get streaming response with stream_options to include token usage
        response_stream = self.get_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stream=True,
            json_response=json_response
        )
        
        full_response = ""
        final_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        
        for chunk in response_stream:
            if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                if callback:
                    callback(content)
            
            # Extract usage information from chunks that contain it
            if hasattr(chunk, 'usage') and chunk.usage:
                final_usage = self._extract_token_usage(chunk)
        
        return full_response, final_usage
