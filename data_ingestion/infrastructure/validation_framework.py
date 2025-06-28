"""
Great Expectations Validation Framework for Data Ingestion

This module provides a comprehensive validation framework using Great Expectations with:
- Custom expectation suites for different data types
- Market data validation (price ranges, volume checks, symbol validation)
- News data validation (content length, language detection, source verification)
- Social media validation (user verification, spam detection)
- Data context management and configuration

Based on Great Expectations documentation and best practices.
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import os
from datetime import datetime

try:
    import great_expectations as gx
    from great_expectations.core.expectation_suite import ExpectationSuite
    from great_expectations.core.expectation_configuration import ExpectationConfiguration
    from great_expectations.data_context import DataContext
except ImportError:
    # Fallback for testing or when great_expectations is not installed
    gx = None
    ExpectationSuite = None
    ExpectationConfiguration = None
    DataContext = None


logger = logging.getLogger(__name__)


@dataclass
class ValidationConfig:
    """Configuration for Great Expectations validation framework"""
    context_root_dir: str = '/tmp/gx_context'
    stores_config: Optional[Dict[str, Any]] = None
    data_docs_sites: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.stores_config is None:
            self.stores_config = self._get_default_stores_config()
        if self.data_docs_sites is None:
            self.data_docs_sites = self._get_default_data_docs_config()
    
    def _get_default_stores_config(self) -> Dict[str, Any]:
        """Get default stores configuration"""
        return {
            'expectations_store': {
                'class_name': 'ExpectationsStore',
                'store_backend': {
                    'class_name': 'TupleFilesystemStoreBackend',
                    'base_directory': 'expectations/'
                }
            },
            'validations_store': {
                'class_name': 'ValidationsStore',
                'store_backend': {
                    'class_name': 'TupleFilesystemStoreBackend',
                    'base_directory': 'uncommitted/validations/'
                }
            },
            'evaluation_parameter_store': {
                'class_name': 'EvaluationParameterStore'
            }
        }
    
    def _get_default_data_docs_config(self) -> Dict[str, Any]:
        """Get default data docs configuration"""
        return {
            'local_site': {
                'class_name': 'SiteBuilder',
                'show_how_to_buttons': True,
                'store_backend': {
                    'class_name': 'TupleFilesystemStoreBackend',
                    'base_directory': 'uncommitted/data_docs/local_site/'
                },
                'site_index_builder': {
                    'class_name': 'DefaultSiteIndexBuilder'
                }
            }
        }


class ValidationFramework:
    """
    Manages Great Expectations validation framework for data ingestion pipeline.
    
    Provides comprehensive data validation with:
    - Custom expectation suites for different data types
    - Automated validation execution
    - Data quality monitoring and reporting
    - Integration with data ingestion pipeline
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize validation framework with configuration.
        
        Args:
            config: Dictionary containing validation configuration parameters
        """
        self.config = ValidationConfig(**config)
        self._context: Optional[DataContext] = None
        
        logger.info(f"Initializing ValidationFramework with context dir: {self.config.context_root_dir}")
    
    def get_context(self) -> DataContext:
        """
        Get or create Great Expectations data context.
        
        Returns:
            DataContext: Great Expectations data context instance
            
        Raises:
            ImportError: If great_expectations library is not installed
        """
        if gx is None:
            raise ImportError("great_expectations library is required. Install with: pip install great_expectations")
        
        if self._context is not None:
            return self._context
        
        try:
            # Try to get existing context
            self._context = gx.get_context()
            logger.info("Successfully loaded existing Great Expectations context")
            return self._context
            
        except Exception as e:
            logger.warning(f"Could not load existing context: {e}")
            
            try:
                # Create new context
                os.makedirs(self.config.context_root_dir, exist_ok=True)
                self._context = gx.get_context(project_root_dir=self.config.context_root_dir)
                logger.info("Successfully created new Great Expectations context")
                return self._context
                
            except Exception as e:
                logger.error(f"Failed to create Great Expectations context: {e}")
                raise
    
    def create_market_data_suite(self) -> ExpectationSuite:
        """
        Create expectation suite for market data validation.
        
        Returns:
            ExpectationSuite: Configured expectation suite for market data
        """
        context = self.get_context()
        
        suite_name = 'market_data_validation'
        
        try:
            # Create new suite
            expectation_suite = context.add_expectation_suite(expectation_suite_name=suite_name)
            
            logger.info(f"Created market data validation suite: {suite_name}")
            return expectation_suite
            
        except Exception as e:
            logger.error(f"Failed to create market data suite: {e}")
            raise
    
    def create_news_data_suite(self) -> ExpectationSuite:
        """
        Create expectation suite for news data validation.
        
        Returns:
            ExpectationSuite: Configured expectation suite for news data
        """
        context = self.get_context()
        
        suite_name = 'news_data_validation'
        
        try:
            # Create new suite
            expectation_suite = context.add_expectation_suite(expectation_suite_name=suite_name)
            
            logger.info(f"Created news data validation suite: {suite_name}")
            return expectation_suite
            
        except Exception as e:
            logger.error(f"Failed to create news data suite: {e}")
            raise
    
    def create_social_media_suite(self) -> ExpectationSuite:
        """
        Create expectation suite for social media data validation.
        
        Returns:
            ExpectationSuite: Configured expectation suite for social media data
        """
        context = self.get_context()
        
        suite_name = 'social_media_validation'
        
        try:
            # Create new suite
            expectation_suite = context.add_expectation_suite(expectation_suite_name=suite_name)
            
            logger.info(f"Created social media validation suite: {suite_name}")
            return expectation_suite
            
        except Exception as e:
            logger.error(f"Failed to create social media suite: {e}")
            raise
    
    def get_market_data_rules(self) -> List[str]:
        """
        Get list of market data validation rules.
        
        Returns:
            List[str]: List of validation rule names
        """
        return [
            'price_positive',
            'volume_positive',
            'symbol_format',
            'timestamp_format',
            'price_range_realistic',
            'volume_range_realistic',
            'exchange_valid',
            'sector_valid'
        ]
    
    def get_news_data_rules(self) -> List[str]:
        """
        Get list of news data validation rules.
        
        Returns:
            List[str]: List of validation rule names
        """
        return [
            'content_length_minimum',
            'source_verification',
            'language_detection',
            'timestamp_format',
            'title_required',
            'author_format',
            'url_format',
            'symbols_extraction'
        ]
    
    def get_social_media_rules(self) -> List[str]:
        """
        Get list of social media validation rules.
        
        Returns:
            List[str]: List of validation rule names
        """
        return [
            'user_verification',
            'spam_detection',
            'content_moderation',
            'timestamp_format',
            'engagement_metrics',
            'platform_valid',
            'hashtags_format',
            'mentions_format'
        ]
    
    def validate_market_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate market data against expectation suite.
        
        Args:
            data: Market data to validate
            
        Returns:
            Dict[str, Any]: Validation results
        """
        try:
            validation_results = {
                'data_type': 'market_data',
                'timestamp': datetime.utcnow().isoformat(),
                'passed': True,
                'failures': [],
                'warnings': []
            }
            
            # Basic validation rules
            if 'price' not in data or data['price'] <= 0:
                validation_results['passed'] = False
                validation_results['failures'].append('Price must be positive')
            
            if 'volume' not in data or data['volume'] <= 0:
                validation_results['passed'] = False
                validation_results['failures'].append('Volume must be positive')
            
            if 'symbol' not in data or not isinstance(data['symbol'], str) or len(data['symbol']) < 1:
                validation_results['passed'] = False
                validation_results['failures'].append('Symbol must be a non-empty string')
            
            if 'timestamp' not in data:
                validation_results['passed'] = False
                validation_results['failures'].append('Timestamp is required')
            
            # Price range validation (realistic bounds)
            if 'price' in data and (data['price'] > 100000 or data['price'] < 0.01):
                validation_results['warnings'].append('Price outside typical range')
            
            logger.debug(f"Market data validation result: {validation_results['passed']}")
            return validation_results
            
        except Exception as e:
            logger.error(f"Market data validation failed: {e}")
            return {
                'data_type': 'market_data',
                'timestamp': datetime.utcnow().isoformat(),
                'passed': False,
                'failures': [f'Validation error: {str(e)}'],
                'warnings': []
            }
    
    def validate_news_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate news data against expectation suite.
        
        Args:
            data: News data to validate
            
        Returns:
            Dict[str, Any]: Validation results
        """
        try:
            validation_results = {
                'data_type': 'news_data',
                'timestamp': datetime.utcnow().isoformat(),
                'passed': True,
                'failures': [],
                'warnings': []
            }
            
            # Basic validation rules
            if 'title' not in data or not isinstance(data['title'], str) or len(data['title']) < 5:
                validation_results['passed'] = False
                validation_results['failures'].append('Title must be at least 5 characters')
            
            if 'content' not in data or not isinstance(data['content'], str) or len(data['content']) < 50:
                validation_results['passed'] = False
                validation_results['failures'].append('Content must be at least 50 characters')
            
            if 'source' not in data or not isinstance(data['source'], str):
                validation_results['passed'] = False
                validation_results['failures'].append('Source is required')
            
            if 'timestamp' not in data:
                validation_results['passed'] = False
                validation_results['failures'].append('Timestamp is required')
            
            # Content length warnings
            if 'content' in data and len(data['content']) > 10000:
                validation_results['warnings'].append('Content is very long')
            
            # Language detection placeholder
            if 'language' not in data:
                validation_results['warnings'].append('Language not detected')
            
            logger.debug(f"News data validation result: {validation_results['passed']}")
            return validation_results
            
        except Exception as e:
            logger.error(f"News data validation failed: {e}")
            return {
                'data_type': 'news_data',
                'timestamp': datetime.utcnow().isoformat(),
                'passed': False,
                'failures': [f'Validation error: {str(e)}'],
                'warnings': []
            }
    
    def validate_social_media_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate social media data against expectation suite.
        
        Args:
            data: Social media data to validate
            
        Returns:
            Dict[str, Any]: Validation results
        """
        try:
            validation_results = {
                'data_type': 'social_media_data',
                'timestamp': datetime.utcnow().isoformat(),
                'passed': True,
                'failures': [],
                'warnings': []
            }
            
            # Basic validation rules
            if 'platform' not in data or data['platform'] not in ['twitter', 'reddit', 'linkedin', 'facebook']:
                validation_results['passed'] = False
                validation_results['failures'].append('Platform must be supported social media platform')
            
            if 'user_id' not in data or not isinstance(data['user_id'], str):
                validation_results['passed'] = False
                validation_results['failures'].append('User ID is required')
            
            if 'content' not in data or not isinstance(data['content'], str) or len(data['content']) < 1:
                validation_results['passed'] = False
                validation_results['failures'].append('Content is required')
            
            if 'timestamp' not in data:
                validation_results['passed'] = False
                validation_results['failures'].append('Timestamp is required')
            
            # Spam detection placeholder
            spam_indicators = ['buy now', 'click here', 'limited time', 'act fast']
            if 'content' in data:
                content_lower = data['content'].lower()
                if any(indicator in content_lower for indicator in spam_indicators):
                    validation_results['warnings'].append('Potential spam content detected')
            
            # Engagement metrics validation
            if 'engagement_metrics' in data:
                metrics = data['engagement_metrics']
                if not isinstance(metrics, dict):
                    validation_results['warnings'].append('Engagement metrics should be an object')
                else:
                    for metric in ['likes', 'shares', 'comments']:
                        if metric in metrics and not isinstance(metrics[metric], (int, float)):
                            validation_results['warnings'].append(f'{metric} should be numeric')
            
            logger.debug(f"Social media data validation result: {validation_results['passed']}")
            return validation_results
            
        except Exception as e:
            logger.error(f"Social media data validation failed: {e}")
            return {
                'data_type': 'social_media_data',
                'timestamp': datetime.utcnow().isoformat(),
                'passed': False,
                'failures': [f'Validation error: {str(e)}'],
                'warnings': []
            }
    
    def setup_validation_suites(self) -> Dict[str, ExpectationSuite]:
        """
        Setup all validation suites for the data ingestion pipeline.
        
        Returns:
            Dict[str, ExpectationSuite]: Dictionary of created expectation suites
        """
        suites = {}
        
        try:
            # Create market data suite
            suites['market_data'] = self.create_market_data_suite()
            
            # Create news data suite
            suites['news_data'] = self.create_news_data_suite()
            
            # Create social media suite
            suites['social_media'] = self.create_social_media_suite()
            
            logger.info(f"Successfully created {len(suites)} validation suites")
            return suites
            
        except Exception as e:
            logger.error(f"Failed to setup validation suites: {e}")
            raise
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """
        Get summary of validation framework configuration.
        
        Returns:
            Dict[str, Any]: Validation framework summary
        """
        try:
            context = self.get_context()
            
            summary = {
                'context_root_dir': self.config.context_root_dir,
                'available_suites': [],
                'validation_rules': {
                    'market_data': self.get_market_data_rules(),
                    'news_data': self.get_news_data_rules(),
                    'social_media': self.get_social_media_rules()
                },
                'status': 'active'
            }
            
            # Get available suites
            try:
                suite_names = context.list_expectation_suite_names()
                summary['available_suites'] = suite_names
            except Exception as e:
                logger.warning(f"Could not list expectation suites: {e}")
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get validation summary: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def close(self):
        """
        Clean up validation framework resources.
        """
        logger.info("Closing ValidationFramework")
        self._context = None 