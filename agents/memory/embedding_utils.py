"""
Embedding Utilities for Memory Layer

This module provides functions for generating vector embeddings from 
trading scenarios and market conditions for episodic memory storage and search.
"""

import json
import logging
from typing import Dict, List, Any, Optional
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Global model instance for reuse
_embedding_model: Optional[SentenceTransformer] = None


def get_embedding_model(model_name: str = "all-MiniLM-L6-v2") -> SentenceTransformer:
    """
    Get or initialize the sentence transformer model.
    
    Args:
        model_name: Name of the sentence transformer model
        
    Returns:
        SentenceTransformer: Initialized model instance
    """
    global _embedding_model
    
    if _embedding_model is None:
        try:
            _embedding_model = SentenceTransformer(model_name)
            logger.info(f"Initialized embedding model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize embedding model {model_name}: {e}")
            raise
    
    return _embedding_model


def generate_scenario_embedding(scenario: Dict[str, Any], model_name: str = "all-MiniLM-L6-v2") -> List[float]:
    """
    Generate vector embedding for a trading scenario.
    
    Args:
        scenario: Trading scenario dictionary containing market conditions, actions, outcomes
        model_name: Name of the sentence transformer model to use
        
    Returns:
        List[float]: Vector embedding of the scenario
        
    Raises:
        ValueError: If scenario is empty or invalid
        RuntimeError: If embedding generation fails
    """
    if not scenario:
        raise ValueError("Scenario cannot be empty")
    
    try:
        # Create text representation of the scenario
        scenario_text = _scenario_to_text(scenario)
        
        # Generate embedding
        model = get_embedding_model(model_name)
        embedding = model.encode(scenario_text, convert_to_tensor=False)
        
        return embedding.tolist()
        
    except Exception as e:
        logger.error(f"Failed to generate embedding for scenario: {e}")
        raise RuntimeError(f"Embedding generation failed: {e}")


def generate_query_embedding(query_conditions: Dict[str, Any], model_name: str = "all-MiniLM-L6-v2") -> List[float]:
    """
    Generate vector embedding for query conditions.
    
    Args:
        query_conditions: Market conditions to search for
        model_name: Name of the sentence transformer model to use
        
    Returns:
        List[float]: Vector embedding of the query
        
    Raises:
        ValueError: If query_conditions is empty
        RuntimeError: If embedding generation fails
    """
    if not query_conditions:
        raise ValueError("Query conditions cannot be empty")
    
    try:
        # Convert query conditions to text
        query_text = _conditions_to_text(query_conditions)
        
        # Generate embedding
        model = get_embedding_model(model_name)
        embedding = model.encode(query_text, convert_to_tensor=False)
        
        return embedding.tolist()
        
    except Exception as e:
        logger.error(f"Failed to generate embedding for query: {e}")
        raise RuntimeError(f"Query embedding generation failed: {e}")


def _scenario_to_text(scenario: Dict[str, Any]) -> str:
    """
    Convert a trading scenario to text representation for embedding.
    
    Args:
        scenario: Trading scenario dictionary
        
    Returns:
        str: Text representation of the scenario
    """
    text_parts = []
    
    # Market conditions
    if "market_conditions" in scenario:
        conditions = scenario["market_conditions"]
        if isinstance(conditions, dict):
            for key, value in conditions.items():
                text_parts.append(f"{key}: {value}")
        else:
            text_parts.append(f"market conditions: {conditions}")
    
    # Actions taken
    if "actions_taken" in scenario:
        actions = scenario["actions_taken"]
        if isinstance(actions, list):
            for action in actions:
                if isinstance(action, dict):
                    agent = action.get("agent", "unknown")
                    action_type = action.get("action", "unknown")
                    confidence = action.get("confidence", 0)
                    text_parts.append(f"{agent} {action_type} confidence {confidence}")
                else:
                    text_parts.append(f"action: {action}")
        else:
            text_parts.append(f"actions: {actions}")
    
    # Action taken (single action format)
    if "action_taken" in scenario:
        action = scenario["action_taken"]
        if isinstance(action, dict):
            signal = action.get("signal", "unknown")
            confidence = action.get("confidence", 0)
            text_parts.append(f"signal {signal} confidence {confidence}")
        else:
            text_parts.append(f"action: {action}")
    
    # Outcomes
    if "outcomes" in scenario or "outcome" in scenario:
        outcome = scenario.get("outcomes", scenario.get("outcome", {}))
        if isinstance(outcome, dict):
            for key, value in outcome.items():
                text_parts.append(f"{key}: {value}")
        else:
            text_parts.append(f"outcome: {outcome}")
    
    # Agent analysis (if available)
    if "agent_analysis" in scenario:
        analysis = scenario["agent_analysis"]
        if isinstance(analysis, dict):
            signal = analysis.get("signal", "")
            reasoning = analysis.get("reasoning", "")
            if signal:
                text_parts.append(f"signal: {signal}")
            if reasoning:
                text_parts.append(f"reasoning: {reasoning}")
    
    # Symbol information
    if "symbol" in scenario:
        text_parts.append(f"symbol: {scenario['symbol']}")
    
    # Join all parts
    return " ".join(text_parts)


def _conditions_to_text(conditions: Dict[str, Any]) -> str:
    """
    Convert market conditions to text representation for embedding.
    
    Args:
        conditions: Market conditions dictionary
        
    Returns:
        str: Text representation of the conditions
    """
    text_parts = []
    
    for key, value in conditions.items():
        if isinstance(value, (list, tuple)):
            text_parts.append(f"{key}: {' '.join(map(str, value))}")
        else:
            text_parts.append(f"{key}: {value}")
    
    return " ".join(text_parts)


def calculate_embedding_similarity(embedding1: List[float], embedding2: List[float]) -> float:
    """
    Calculate cosine similarity between two embeddings.
    
    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector
        
    Returns:
        float: Cosine similarity score between 0 and 1
        
    Raises:
        ValueError: If embeddings have different dimensions
    """
    if len(embedding1) != len(embedding2):
        raise ValueError("Embeddings must have the same dimension")
    
    # Convert to numpy arrays
    vec1 = np.array(embedding1)
    vec2 = np.array(embedding2)
    
    # Calculate cosine similarity
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    similarity = dot_product / (norm1 * norm2)
    
    # Ensure result is between 0 and 1
    return max(0.0, min(1.0, (similarity + 1) / 2))


def batch_generate_embeddings(scenarios: List[Dict[str, Any]], model_name: str = "all-MiniLM-L6-v2") -> List[List[float]]:
    """
    Generate embeddings for multiple scenarios in batch for efficiency.
    
    Args:
        scenarios: List of trading scenario dictionaries
        model_name: Name of the sentence transformer model to use
        
    Returns:
        List[List[float]]: List of vector embeddings
        
    Raises:
        ValueError: If scenarios list is empty
        RuntimeError: If batch embedding generation fails
    """
    if not scenarios:
        raise ValueError("Scenarios list cannot be empty")
    
    try:
        # Convert all scenarios to text
        scenario_texts = [_scenario_to_text(scenario) for scenario in scenarios]
        
        # Generate embeddings in batch
        model = get_embedding_model(model_name)
        embeddings = model.encode(scenario_texts, convert_to_tensor=False)
        
        return [embedding.tolist() for embedding in embeddings]
        
    except Exception as e:
        logger.error(f"Failed to generate batch embeddings: {e}")
        raise RuntimeError(f"Batch embedding generation failed: {e}") 