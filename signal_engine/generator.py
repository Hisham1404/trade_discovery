import shap
import numpy as np
import pandas as pd
import json
import asyncio
import logging
from typing import List, Dict, Optional
from collections import defaultdict
from datetime import datetime, timezone
import time

import pulsar
from sqlalchemy.orm import Session

# Import database models (will be used once available)
try:
    from app.models.signal import Signal
except ImportError:
    # Fallback for development
    class Signal:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

logger = logging.getLogger(__name__)

class SignalGenerator:
    """
    Core Signal Generation Engine implementing Task 6 requirements:
    - Pulsar-based multi-agent signal aggregation
    - SHAP-based explainability 
    - Natural language explanations
    - Confidence scoring and signal ranking
    """
    
    def __init__(self, db_session: Session, pulsar_url: str = 'pulsar://pulsar:6650'):
        """Initialize SignalGenerator with database and Pulsar connections"""
        self.db = db_session
        self.pulsar_url = pulsar_url
        
        # Initialize Pulsar client and consumer
        self.pulsar_client = pulsar.Client(pulsar_url)
        self.consumer = self.pulsar_client.subscribe(
            topics=[
                'signals.dapo.enhanced',
                'signals.gemma.financial', 
                'signals.cmg.chaos',
                'signals.sert.price'
            ],
            subscription_name='signal-aggregator'
        )
        
        # Agent performance weights for confidence calculation
        self.agent_weights = {
            'DAPO Signal Generator': 0.3,
            'Gemma-7B Financial': 0.25,
            'CMG Chaos Predictor': 0.2,
            'SERT Price Transformer': 0.25
        }
        
        # Initialize SHAP explainer
        self._initialize_shap_explainer()
        
        logger.info("SignalGenerator initialized with Pulsar integration")
    
    def _initialize_shap_explainer(self):
        """Initialize SHAP explainer for feature attribution"""
        # Define feature names for explainability
        self.feature_names = ['technical_score', 'sentiment_score', 'fundamental_score', 'risk_score']
        
        # Create a simple explainer function for SHAP
        def explain_signal(features):
            """Simple signal explanation function for SHAP"""
            # Basic weighted combination for demonstration
            weights = np.array([0.3, 0.4, 0.2, 0.1])  # tech, sentiment, fundamental, risk
            if features.ndim == 1:
                return np.dot(features, weights)
            else:
                return np.dot(features, weights)
        
        # Create background data for masker (typical feature ranges)
        background_data = np.array([
            [0.5, 0.5, 0.5, 0.5],  # Neutral baseline
            [0.0, 0.0, 0.0, 0.0],  # Minimum values
            [1.0, 1.0, 1.0, 1.0],  # Maximum values
            [0.3, 0.4, 0.3, 0.2],  # Typical low values
            [0.7, 0.8, 0.7, 0.6],  # Typical high values
        ])
        
        # Initialize SHAP explainer with background data as masker
        self.explainer = shap.Explainer(explain_signal, background_data)
        logger.info("SHAP explainer initialized with background masker")
    
    async def aggregate_agent_signals(self, timeout_ms: int = 1000) -> List[Dict]:
        """
        Aggregate signals from multiple agents via Pulsar topics
        
        Args:
            timeout_ms: Timeout for receiving messages in milliseconds
            
        Returns:
            List of agent signals with metadata
        """
        signals = []
        
        try:
            while True:
                try:
                    # Receive message with timeout
                    msg = self.consumer.receive(timeout_millis=timeout_ms)
                    
                    if msg:
                        # Parse signal data
                        signal_data = json.loads(msg.data().decode('utf-8'))
                        signals.append(signal_data)
                        
                        # Acknowledge successful processing
                        self.consumer.acknowledge(msg)
                        
                        logger.debug(f"Received signal from {signal_data.get('agent', 'unknown')}")
                    
                except Exception as e:
                    # Timeout or other error - break the loop
                    logger.debug(f"Signal aggregation timeout or error: {e}")
                    break
                        
        except Exception as e:
            logger.error(f"Error in signal aggregation: {e}")
        
        logger.info(f"Aggregated {len(signals)} signals from agents")
        return signals
    
    def _group_signals_by_symbol(self, signals: List[Dict]) -> Dict[str, List[Dict]]:
        """Group signals by symbol for processing"""
        symbol_signals = defaultdict(list)
        
        for signal in signals:
            symbol = signal.get('symbol')
            if symbol:
                symbol_signals[symbol].append(signal)
        
        return dict(symbol_signals)
    
    def calculate_composite_confidence(self, agent_signals: List[Dict]) -> float:
        """
        Calculate weighted composite confidence based on agent performance
        
        Args:
            agent_signals: List of signals from different agents for same symbol
            
        Returns:
            Composite confidence score (0.0 to 1.0)
        """
        if not agent_signals:
            return 0.0
        
        weighted_sum = 0.0
        total_weight = 0.0
        
        for signal in agent_signals:
            agent = signal.get('agent', 'unknown')
            confidence = signal.get('confidence', 0.0)
            weight = self.agent_weights.get(agent, 0.1)  # Default weight for unknown agents
            
            weighted_sum += confidence * weight
            total_weight += weight
        
        # Normalize by total weight of participating agents
        composite_confidence = weighted_sum / total_weight if total_weight > 0 else 0.0
        
        # Ensure result is within valid range
        return min(max(composite_confidence, 0.0), 1.0)
    
    def generate_shap_explanation(self, signal_data: Dict) -> Dict:
        """
        Generate SHAP-based feature attribution explanation
        
        Args:
            signal_data: Signal data with feature scores
            
        Returns:
            SHAP explanation with feature importance and top factors
        """
        start_time = time.time()
        
        try:
            # Create feature matrix from signal data
            features = np.array([
                signal_data.get('technical_score', 0.0),
                signal_data.get('sentiment_score', 0.0),
                signal_data.get('fundamental_score', 0.0),
                signal_data.get('risk_score', 0.0)
            ])
            
            # Calculate SHAP values
            shap_values = self.explainer(features.reshape(1, -1))
            
            # Extract SHAP values (handle different SHAP output formats)
            if hasattr(shap_values, 'values'):
                values = shap_values.values[0]
            else:
                values = shap_values[0] if isinstance(shap_values, (list, np.ndarray)) else shap_values
            
            # Create feature importance dictionary
            feature_importance = {
                'technical': float(values[0]),
                'sentiment': float(values[1]),
                'fundamental': float(values[2]),
                'risk': float(values[3])
            }
            
            # Get top contributing factors
            top_factors = self._get_top_factors(values)
            
            processing_time = (time.time() - start_time) * 1000
            logger.debug(f"SHAP explanation generated in {processing_time:.2f}ms")
            
            return {
                'feature_importance': feature_importance,
                'top_factors': top_factors,
                'processing_time_ms': processing_time
            }
            
        except Exception as e:
            logger.error(f"Error generating SHAP explanation: {e}")
            return {
                'feature_importance': {name: 0.0 for name in self.feature_names},
                'top_factors': [],
                'error': str(e)
            }
    
    def _get_top_factors(self, shap_values: np.ndarray, top_k: int = 2) -> List[Dict]:
        """
        Identify top contributing factors from SHAP values
        
        Args:
            shap_values: Array of SHAP values for features
            top_k: Number of top factors to return
            
        Returns:
            List of top factors with names and impact scores
        """
        # Create factor list with absolute importance
        factors = []
        for i, (name, value) in enumerate(zip(self.feature_names, shap_values)):
            factors.append({
                'name': name,
                'impact': float(value),
                'abs_impact': abs(float(value))
            })
        
        # Sort by absolute impact and return top k
        factors.sort(key=lambda x: x['abs_impact'], reverse=True)
        return factors[:top_k]
    
    def generate_natural_language_explanation(self, signal: Dict, shap_data: Dict) -> str:
        """
        Generate natural language explanation for signal
        
        Args:
            signal: Signal data with direction, confidence, etc.
            shap_data: SHAP explanation data
            
        Returns:
            Natural language explanation string
        """
        try:
            top_factors = shap_data.get('top_factors', [])
            primary_driver = self._get_primary_driver(shap_data)
            
            # Create explanation template
            template = f"""
{signal['direction'].capitalize()} signal for {signal['symbol']} with {signal['confidence']:.1%} confidence.

Key drivers:"""
            
            # Add top factors if available
            if len(top_factors) >= 2:
                template += f"""
- {top_factors[0]['name']}: {top_factors[0]['impact']:.3f} impact
- {top_factors[1]['name']}: {top_factors[1]['impact']:.3f} impact"""
            
            template += f"""

The signal is primarily driven by {primary_driver} factors, suggesting a {signal['direction']} position with target at ₹{signal.get('target', 0):.2f} and stop-loss at ₹{signal.get('stop_loss', 0):.2f}."""
            
            return template.strip()
            
        except Exception as e:
            logger.error(f"Error generating natural language explanation: {e}")
            return f"Signal explanation unavailable due to error: {str(e)}"
    
    def _get_primary_driver(self, shap_data: Dict) -> str:
        """Identify primary driving factor from SHAP data"""
        top_factors = shap_data.get('top_factors', [])
        
        if top_factors:
            primary_factor = top_factors[0]['name']
            return primary_factor
        
        return "technical"  # Default fallback
    
    def _store_signal(self, signal_data: Dict) -> Signal:
        """
        Store processed signal in database
        
        Args:
            signal_data: Complete signal data with explanations
            
        Returns:
            Stored Signal object
        """
        try:
            db_signal = Signal(
                symbol=signal_data['symbol'],
                direction=signal_data['direction'],
                confidence=signal_data['confidence'],
                stop_loss=signal_data.get('stop_loss'),
                target=signal_data.get('target'),
                generating_agent='Multi-Agent Consensus',
                rationale=signal_data.get('explanation', ''),
                shap_values=signal_data.get('shap_values', {}),
                created_at=datetime.now(timezone.utc)
            )
            
            self.db.add(db_signal)
            self.db.commit()
            
            logger.info(f"Signal stored for {signal_data['symbol']}")
            return db_signal
            
        except Exception as e:
            logger.error(f"Error storing signal: {e}")
            self.db.rollback()
            raise
    
    async def generate_and_store_signals(self, confidence_threshold: float = 0.6):
        """
        Main pipeline: Aggregate signals, generate explanations, and store results
        
        Args:
            confidence_threshold: Minimum confidence threshold for signal acceptance
        """
        start_time = time.time()
        
        try:
            # Step 1: Aggregate signals from Pulsar
            agent_signals = await self.aggregate_agent_signals()
            
            if not agent_signals:
                logger.info("No signals received from agents")
                return
            
            # Step 2: Group signals by symbol
            symbol_signals = self._group_signals_by_symbol(agent_signals)
            
            # Step 3: Process each symbol's signals
            for symbol, signals in symbol_signals.items():
                try:
                    # Calculate composite confidence
                    confidence = self.calculate_composite_confidence(signals)
                    
                    # Filter by confidence threshold
                    if confidence <= confidence_threshold:
                        logger.debug(f"Signal for {symbol} filtered out (confidence: {confidence:.3f})")
                        continue
                    
                    # Use the first signal as base (could be enhanced to merge multiple signals)
                    base_signal = signals[0].copy()
                    base_signal['confidence'] = confidence
                    
                    # Step 4: Generate SHAP explanation
                    shap_data = self.generate_shap_explanation(base_signal)
                    
                    # Step 5: Generate natural language explanation
                    explanation = self.generate_natural_language_explanation(base_signal, shap_data)
                    
                    # Step 6: Prepare final signal data
                    final_signal = {
                        'symbol': symbol,
                        'direction': base_signal['direction'],
                        'confidence': confidence,
                        'target': base_signal.get('target'),
                        'stop_loss': base_signal.get('stop_loss'),
                        'explanation': explanation,
                        'shap_values': shap_data
                    }
                    
                    # Step 7: Store in database
                    self._store_signal(final_signal)
                    
                    logger.info(f"Generated signal for {symbol} with {confidence:.1%} confidence")
                    
                except Exception as e:
                    logger.error(f"Error processing signals for {symbol}: {e}")
                    continue
            
            processing_time = (time.time() - start_time) * 1000
            logger.info(f"Signal generation pipeline completed in {processing_time:.2f}ms")
            
        except Exception as e:
            logger.error(f"Error in signal generation pipeline: {e}")
            raise
    
    def close(self):
        """Close Pulsar connections and cleanup resources"""
        try:
            self.consumer.close()
            self.pulsar_client.close()
            logger.info("SignalGenerator connections closed")
        except Exception as e:
            logger.error(f"Error closing connections: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup"""
        self.close() 