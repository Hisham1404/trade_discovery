import asyncio
import json
import re
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
import logging
from collections import defaultdict, deque

import feedparser
import tweepy
import praw
from transformers import pipeline
import torch

from ..infrastructure.pulsar_client import PulsarManager
from ..infrastructure.elasticsearch_client import ElasticsearchManager

logger = logging.getLogger(__name__)


class SymbolExtractor:
    """
    Symbol extraction using regex patterns and whitelisting.
    
    Extracts stock symbols from text using configurable patterns
    and validates against a whitelist of known symbols.
    """
    
    def __init__(self, patterns: List[str], whitelist: List[str]):
        self.patterns = [re.compile(pattern) for pattern in patterns]
        self.whitelist = set(whitelist)
        
        # Context patterns for confidence scoring
        self.stock_context_patterns = [
            re.compile(r'\b(stock|share|equity|price|trading|market)\b', re.IGNORECASE),
            re.compile(r'\b(buy|sell|hold|target|returns|dividend)\b', re.IGNORECASE),
            re.compile(r'\b(earnings|results|revenue|profit|growth)\b', re.IGNORECASE)
        ]
    
    def extract(self, text: str) -> List[str]:
        """Extract symbols from text using patterns and whitelist."""
        symbols = set()
        
        for pattern in self.patterns:
            matches = pattern.findall(text)
            for match in matches:
                # Handle tuple results from group captures
                symbol = match if isinstance(match, str) else match[0] if match else ''
                symbol = symbol.upper().strip()
                
                if symbol in self.whitelist:
                    symbols.add(symbol)
        
        return list(symbols)
    
    def extract_with_confidence(self, text: str) -> List[Dict[str, Any]]:
        """Extract symbols with confidence scores based on context."""
        symbols = self.extract(text)
        results = []
        
        for symbol in symbols:
            # Calculate confidence based on context
            confidence = 0.5  # Base confidence
            
            # Check for stock-related context around the symbol
            symbol_positions = [m.start() for m in re.finditer(rf'\b{symbol}\b', text, re.IGNORECASE)]
            
            for pos in symbol_positions:
                # Check context window around symbol (50 chars each side)
                start = max(0, pos - 50)
                end = min(len(text), pos + len(symbol) + 50)
                context = text[start:end]
                
                # Count context matches
                context_score = sum(1 for pattern in self.stock_context_patterns if pattern.search(context))
                confidence += context_score * 0.15
            
            results.append({
                'symbol': symbol,
                'confidence': min(confidence, 1.0)
            })
        
        return results


class SentimentAnalyzer:
    """
    Financial sentiment analysis using pre-trained transformers models.
    
    Uses FinBERT or similar models for financial text sentiment classification.
    """
    
    def __init__(self, model_name: str = 'ProsusAI/finbert'):
        self.model_name = model_name
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        try:
            # Initialize sentiment analysis pipeline with FinBERT
            self.classifier = pipeline(
                'sentiment-analysis',
                model=model_name,
                return_all_scores=True,
                device=0 if self.device == 'cuda' else -1
            )
            logger.info(f"Sentiment analyzer initialized with {model_name} on {self.device}")
        except Exception as e:
            logger.error(f"Failed to initialize sentiment model {model_name}: {e}")
            # Fallback to default model
            self.classifier = pipeline('sentiment-analysis', return_all_scores=True)
    
    def analyze(self, text: str) -> Dict[str, Union[str, float]]:
        """Analyze sentiment of a single text."""
        try:
            results = self.classifier(text)
            # Get the highest scoring sentiment
            best_result = max(results[0], key=lambda x: x['score'])
            
            return {
                'label': best_result['label'],
                'score': float(best_result['score'])
            }
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return {'label': 'NEUTRAL', 'score': 0.5}
    
    def analyze_batch(self, texts: List[str]) -> List[Dict[str, Union[str, float]]]:
        """Analyze sentiment for multiple texts efficiently."""
        try:
            batch_results = self.classifier(texts)
            
            results = []
            for result_set in batch_results:
                best_result = max(result_set, key=lambda x: x['score'])
                results.append({
                    'label': best_result['label'],
                    'score': float(best_result['score'])
                })
            
            return results
        except Exception as e:
            logger.error(f"Batch sentiment analysis failed: {e}")
            return [{'label': 'NEUTRAL', 'score': 0.5} for _ in texts]


class NewsSentimentIngestion:
    """
    Comprehensive News and Social Media Sentiment Ingestion Pipeline.
    
    Features:
    - RSS feed parsing (Reuters, Bloomberg, Economic Times)
    - Twitter streaming with keyword filtering
    - Reddit subreddit monitoring
    - Symbol extraction with confidence scoring
    - Financial sentiment analysis using FinBERT
    - Real-time data storage to Pulsar and Elasticsearch
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        pulsar_manager: PulsarManager,
        elasticsearch_manager: ElasticsearchManager
    ):
        self.config = config
        self.pulsar_manager = pulsar_manager
        self.elasticsearch_manager = elasticsearch_manager
        
        # Initialize components
        self.sentiment_analyzer = SentimentAnalyzer(
            model_name=config['sentiment']['model_name']
        )
        self.symbol_extractor = SymbolExtractor(
            patterns=config['symbol_extraction']['patterns'],
            whitelist=config['symbol_extraction']['whitelisted_symbols']
        )
        
        # Social media clients
        self.twitter_client = None
        self.reddit_client = None
        
        # State management
        self.is_running = False
        self.last_rss_update = None
        self.last_social_update = None
        
        # Performance metrics
        self.metrics = defaultdict(int)
        self.processing_times = deque(maxlen=100)
        
        # Deduplication cache (TTL: 1 hour)
        self.content_cache = {}
        self.cache_expiry = {}
        
        # Background tasks
        self.background_tasks = []
    
    async def start(self):
        """Start the sentiment ingestion service."""
        if self.is_running:
            logger.warning("Service is already running")
            return
        
        logger.info("Starting News and Social Media Sentiment Ingestion Service")
        
        # Initialize social media clients
        await self._initialize_social_clients()
        
        # Start background tasks
        await self._start_background_tasks()
        
        self.is_running = True
        logger.info("Sentiment ingestion service started successfully")
    
    async def stop(self):
        """Stop the sentiment ingestion service."""
        if not self.is_running:
            return
        
        logger.info("Stopping sentiment ingestion service")
        
        # Stop background tasks
        await self._stop_background_tasks()
        
        # Close social media connections
        if self.twitter_client:
            # Twitter client cleanup if needed
            pass
        
        self.is_running = False
        logger.info("Sentiment ingestion service stopped")
    
    async def _initialize_social_clients(self):
        """Initialize Twitter and Reddit API clients."""
        try:
            # Initialize Twitter client with Context7 best practices
            twitter_config = self.config['social_media']['twitter']
            self.twitter_client = tweepy.Client(
                bearer_token=twitter_config['bearer_token'],
                wait_on_rate_limit=True
            )
            
            # Initialize Reddit client
            reddit_config = self.config['social_media']['reddit']
            self.reddit_client = praw.Reddit(
                client_id=reddit_config['client_id'],
                client_secret=reddit_config['client_secret'],
                user_agent=reddit_config['user_agent']
            )
            
            logger.info("Social media clients initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize social media clients: {e}")
    
    async def _start_background_tasks(self):
        """Start background processing tasks."""
        # RSS feed monitoring
        rss_task = asyncio.create_task(self._rss_monitoring_loop())
        self.background_tasks.append(rss_task)
        
        # Twitter monitoring
        twitter_task = asyncio.create_task(self._twitter_monitoring_loop())
        self.background_tasks.append(twitter_task)
        
        # Reddit monitoring
        reddit_task = asyncio.create_task(self._reddit_monitoring_loop())
        self.background_tasks.append(reddit_task)
        
        # Cache cleanup
        cleanup_task = asyncio.create_task(self._cache_cleanup_loop())
        self.background_tasks.append(cleanup_task)
    
    async def _stop_background_tasks(self):
        """Stop all background tasks."""
        for task in self.background_tasks:
            task.cancel()
        
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        self.background_tasks.clear()
    
    async def fetch_rss_articles(self, feed_url: str) -> List[Dict[str, Any]]:
        """
        Fetch and process RSS articles using feedparser.
        
        Based on Context7 feedparser documentation patterns.
        """
        try:
            # Parse RSS feed with feedparser (Context7 pattern)
            feed_data = feedparser.parse(feed_url)
            
            if feed_data.bozo:
                logger.warning(f"RSS feed parsing warnings for {feed_url}: {feed_data.bozo_exception}")
            
            articles = []
            for entry in feed_data.entries:
                # Extract article content
                content = f"{entry.get('title', '')} {entry.get('description', '')}"
                
                # Check for duplicates
                if self.is_duplicate_content(content):
                    continue
                
                # Extract symbols
                extracted_symbols = self.extract_symbols(content)
                
                # Skip if no relevant symbols found
                if not extracted_symbols:
                    continue
                
                article = {
                    'id': entry.get('id', entry.get('link', '')),
                    'title': entry.get('title', ''),
                    'content': entry.get('description', ''),
                    'url': entry.get('link', ''),
                    'published': self._parse_date(entry.get('published', '')),
                    'source': 'RSS',
                    'feed_url': feed_url,
                    'extracted_symbols': extracted_symbols,
                    'timestamp': datetime.now().isoformat()
                }
                
                articles.append(article)
                self.mark_content_processed(content)
            
            self.metrics['rss_articles_processed'] += len(articles)
            return articles
            
        except Exception as e:
            logger.error(f"Failed to fetch RSS articles from {feed_url}: {e}")
            return []
    
    async def process_social_media_post(self, post_data: Dict[str, Any], platform: str) -> Dict[str, Any]:
        """Process social media post with sentiment analysis."""
        start_time = time.time()
        
        try:
            # Extract text content based on platform
            if platform == 'twitter':
                content = post_data.get('text', '')
                post_id = post_data.get('id', '')
                author = post_data.get('author', {}).get('username', '')
                metrics = post_data.get('public_metrics', {})
            elif platform == 'reddit':
                content = f"{post_data.get('title', '')} {post_data.get('selftext', '')}"
                post_id = post_data.get('id', '')
                author = post_data.get('author', '')
                metrics = {
                    'score': post_data.get('score', 0),
                    'num_comments': post_data.get('num_comments', 0)
                }
            else:
                raise ValueError(f"Unsupported platform: {platform}")
            
            # Check for duplicates
            if self.is_duplicate_content(content):
                return None
            
            # Extract symbols
            extracted_symbols = self.extract_symbols(content)
            if not extracted_symbols:
                return None
            
            # Analyze sentiment
            sentiment = self.sentiment_analyzer.analyze(content)
            
            processed_post = {
                'id': post_id,
                'platform': platform,
                'content': content,
                'author': author,
                'metrics': metrics,
                'extracted_symbols': extracted_symbols,
                'sentiment': sentiment,
                'timestamp': datetime.now().isoformat(),
                'source': 'social_media'
            }
            
            self.mark_content_processed(content)
            self.metrics[f'{platform}_posts_processed'] += 1
            
            # Track processing time
            processing_time = time.time() - start_time
            self.processing_times.append(processing_time)
            
            return processed_post
            
        except Exception as e:
            logger.error(f"Failed to process {platform} post: {e}")
            return None
    
    def extract_symbols(self, text: str) -> List[str]:
        """Extract stock symbols from text."""
        return self.symbol_extractor.extract(text)
    
    def analyze_sentiment(self, texts: List[str]) -> List[Dict[str, Union[str, float]]]:
        """Analyze sentiment for multiple texts."""
        self.metrics['sentiment_analysis_calls'] += len(texts)
        return self.sentiment_analyzer.analyze_batch(texts)
    
    def analyze_sentiment_batch(self, texts: List[str]) -> List[Dict[str, Union[str, float]]]:
        """Batch sentiment analysis for efficiency."""
        return self.sentiment_analyzer.analyze_batch(texts)
    
    def is_duplicate_content(self, content: str) -> bool:
        """Check if content has been processed recently."""
        content_hash = self.generate_content_hash(content)
        
        # Clean expired entries
        current_time = time.time()
        expired_keys = [k for k, exp_time in self.cache_expiry.items() if current_time > exp_time]
        for key in expired_keys:
            self.content_cache.pop(key, None)
            self.cache_expiry.pop(key, None)
        
        return content_hash in self.content_cache
    
    def mark_content_processed(self, content: str):
        """Mark content as processed with TTL."""
        content_hash = self.generate_content_hash(content)
        self.content_cache[content_hash] = True
        self.cache_expiry[content_hash] = time.time() + 3600  # 1 hour TTL
    
    def generate_content_hash(self, content: str) -> str:
        """Generate hash for content deduplication."""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    async def store_sentiment_data(self, data: Dict[str, Any], data_type: str):
        """Store sentiment data to Pulsar and Elasticsearch."""
        try:
            # Determine topic and index based on data type
            if data_type == 'news':
                topic = self.config['pulsar']['topics']['news_sentiment']
                index = self.config['elasticsearch']['indices']['news_sentiment']
            else:  # social media
                topic = self.config['pulsar']['topics']['social_sentiment']
                index = self.config['elasticsearch']['indices']['social_sentiment']
            
            # Send to Pulsar
            try:
                producer = await self.pulsar_manager.get_producer(topic)
                await producer.send_async(json.dumps(data).encode('utf-8'))
            except Exception as e:
                logger.error(f"Failed to send to Pulsar: {e}")
            
            # Index in Elasticsearch
            try:
                await self.elasticsearch_manager.index_document(
                    index=index,
                    doc=data,
                    doc_id=data.get('id')
                )
            except Exception as e:
                logger.error(f"Failed to index in Elasticsearch: {e}")
        
        except Exception as e:
            logger.error(f"Failed to store sentiment data: {e}")
    
    async def _rss_monitoring_loop(self):
        """Background task for RSS feed monitoring."""
        while self.is_running:
            try:
                for feed_url in self.config['news_sources']['rss_feeds']:
                    articles = await self.fetch_rss_articles(feed_url)
                    
                    for article in articles:
                        # Add sentiment analysis
                        sentiment = self.sentiment_analyzer.analyze(article['content'])
                        article['sentiment'] = sentiment
                        
                        # Store processed article
                        await self.store_sentiment_data(article, 'news')
                
                self.last_rss_update = datetime.now()
                
                # Wait for next update
                await asyncio.sleep(self.config['news_sources']['update_interval'])
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"RSS monitoring error: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _twitter_monitoring_loop(self):
        """Background task for Twitter monitoring."""
        # Implementation would use Twitter streaming API
        # This is a placeholder for the streaming logic
        while self.is_running:
            try:
                # Twitter streaming would be implemented here
                # Using tweepy.StreamingClient with Context7 patterns
                await asyncio.sleep(30)  # Placeholder
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Twitter monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def _reddit_monitoring_loop(self):
        """Background task for Reddit monitoring."""
        while self.is_running:
            try:
                if not self.reddit_client:
                    await asyncio.sleep(60)
                    continue
                
                for subreddit_name in self.config['social_media']['reddit']['subreddits']:
                    subreddit = self.reddit_client.subreddit(subreddit_name)
                    
                    # Get recent posts
                    for post in subreddit.new(limit=10):
                        post_data = {
                            'id': post.id,
                            'title': post.title,
                            'selftext': post.selftext,
                            'score': post.score,
                            'num_comments': post.num_comments,
                            'created_utc': post.created_utc,
                            'author': str(post.author),
                            'subreddit': subreddit_name
                        }
                        
                        processed_post = await self.process_social_media_post(post_data, 'reddit')
                        if processed_post:
                            await self.store_sentiment_data(processed_post, 'social')
                
                self.last_social_update = datetime.now()
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reddit monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def _cache_cleanup_loop(self):
        """Background task for cache cleanup."""
        while self.is_running:
            try:
                current_time = time.time()
                expired_keys = [k for k, exp_time in self.cache_expiry.items() if current_time > exp_time]
                
                for key in expired_keys:
                    self.content_cache.pop(key, None)
                    self.cache_expiry.pop(key, None)
                
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
                await asyncio.sleep(300)  # Cleanup every 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
                await asyncio.sleep(300)
    
    def _parse_date(self, date_str: str) -> str:
        """Parse date string to ISO format."""
        try:
            # Handle various date formats
            if date_str:
                # Use feedparser's date parsing capability
                parsed_time = feedparser._parse_date(date_str)
                if parsed_time:
                    return datetime(*parsed_time[:6]).isoformat()
        except:
            pass
        
        return datetime.now().isoformat()
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        avg_processing_time = (
            sum(self.processing_times) / len(self.processing_times)
            if self.processing_times else 0
        )
        
        return {
            'rss_articles_processed': self.metrics['rss_articles_processed'],
            'social_posts_processed': sum(
                self.metrics[f'{platform}_posts_processed']
                for platform in ['twitter', 'reddit']
            ),
            'sentiment_analysis_calls': self.metrics['sentiment_analysis_calls'],
            'average_processing_time': avg_processing_time,
            'error_count': self.metrics['error_count'],
            'cache_size': len(self.content_cache)
        }
    
    def update_metrics(self, metric_name: str, value: int):
        """Update performance metrics."""
        self.metrics[metric_name] += value
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status information."""
        return {
            'is_running': self.is_running,
            'last_rss_update': self.last_rss_update.isoformat() if self.last_rss_update else None,
            'last_social_update': self.last_social_update.isoformat() if self.last_social_update else None,
            'performance_metrics': self.get_performance_metrics(),
            'active_background_tasks': len(self.background_tasks)
        } 