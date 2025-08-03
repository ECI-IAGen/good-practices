import os
from enum import Enum
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Cargar variables de entorno al importar el módulo
load_dotenv()

class LLMProvider(Enum):
    """Enum para los proveedores de LLM disponibles"""
    OPENAI = "openai"
    DEEPSEEK = "deepseek"

class LLMFactory:
    """Factory class para crear instancias de LLM de manera fácil"""
    
    # Configuraciones predefinidas para cada proveedor
    PROVIDER_CONFIGS = {
        LLMProvider.OPENAI: {
            "base_url": None,  # Usa la URL por defecto de OpenAI
            "model_default": "gpt-4o",
            "api_key_env": "OPENAI_API_KEY"
        },
        LLMProvider.DEEPSEEK: {
            "base_url": "https://api.deepseek.com/v1",
            "model_default": "deepseek-coder",
            "api_key_env": "DEEP_SEEK_API_KEY"
        }
    }
    
    @classmethod
    def create_llm(
        self,
        provider: LLMProvider,
        model: Optional[str] = None,
        temperature: float = 0,
        timeout: int = 60,
        max_retries: int = 3,
        api_key: Optional[str] = None,
        **kwargs
    ) -> ChatOpenAI:
        """
        Crea una instancia de ChatOpenAI configurada para el proveedor especificado.
        
        Args:
            provider: El proveedor de LLM (OPENAI o DEEPSEEK)
            model: Modelo específico a usar (opcional, usa el por defecto del proveedor)
            temperature: Temperatura para la generación (0-2)
            timeout: Timeout en segundos
            max_retries: Número máximo de reintentos
            api_key: API key específica (opcional, usa la variable de entorno)
            **kwargs: Argumentos adicionales para ChatOpenAI
            
        Returns:
            ChatOpenAI: Instancia configurada del LLM
            
        Raises:
            ValueError: Si no se encuentra la API key
            KeyError: Si el proveedor no es válido
        """
        
        if provider not in self.PROVIDER_CONFIGS:
            raise KeyError(f"Proveedor no soportado: {provider}")
        
        config = self.PROVIDER_CONFIGS[provider]
        
        # Usar modelo por defecto si no se especifica
        if model is None:
            model = config["model_default"]
        
        # Obtener API key de variable de entorno si no se proporciona
        if api_key is None:
            api_key = os.getenv(config["api_key_env"])
            if not api_key:
                raise ValueError(
                    f"API key no encontrada. Establece la variable de entorno {config['api_key_env']} "
                    f"o proporciona el parámetro api_key"
                )
        
        # Configuración base
        llm_config = {
            "model": model,
            "api_key": api_key,
            "temperature": temperature,
            "timeout": timeout,
            "max_retries": max_retries,
            **kwargs
        }
        
        # Agregar base_url si está definida
        if config["base_url"]:
            llm_config["base_url"] = config["base_url"]
        
        return ChatOpenAI(**llm_config)
    
    @classmethod
    def create_openai_llm(
        self,
        model: str = "gpt-4o",
        temperature: float = 0,
        **kwargs
    ) -> ChatOpenAI:
        """
        Método de conveniencia para crear un LLM de OpenAI.
        
        Args:
            model: Modelo de OpenAI a usar
            temperature: Temperatura para la generación
            **kwargs: Argumentos adicionales
            
        Returns:
            ChatOpenAI: Instancia configurada para OpenAI
        """
        return self.create_llm(
            provider=LLMProvider.OPENAI,
            model=model,
            temperature=temperature,
            **kwargs
        )
    
    @classmethod
    def create_deepseek_llm(
        self,
        model: str = "deepseek-coder",
        temperature: float = 0,
        **kwargs
    ) -> ChatOpenAI:
        """
        Método de conveniencia para crear un LLM de DeepSeek.
        
        Args:
            model: Modelo de DeepSeek a usar
            temperature: Temperatura para la generación
            **kwargs: Argumentos adicionales
            
        Returns:
            ChatOpenAI: Instancia configurada para DeepSeek
        """
        return self.create_llm(
            provider=LLMProvider.DEEPSEEK,
            model=model,
            temperature=temperature,
            **kwargs
        )
