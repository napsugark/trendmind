#!/usr/bin/env python3
"""
Data Orchestrator for TrendMind

This script handles the end-to-end data collection workflow:
1. Parse input sources (URLs/handles)
2. Determine source types (Twitter, RSS, Substack)
3. Check database for existing data
4. Run appropriate scrapers
5. Save results to database
6. Return consolidated results for frontend

Usage:
    python get_data.py --sources-file data/sources.txt
    python get_data.py --sources "url1,url2,url3"
    python get_data.py --interactive
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from pathlib import Path

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
from src.scraper import (
    scrape_blog_or_rss, 
    scrape_twitter, 
    scrape_substack_research,
    check_and_scrape
)
from src.db_postgres import (
    connect_postgres,
    insert_posts,
    get_existing_articles,
    get_articles_for_processing,
    get_article_count_by_source
)
from utils.logger import get_logger, log_performance

# Load environment variables
load_dotenv()

class SourceType:
    """Source type constants"""
    TWITTER = "twitter"
    RSS = "rss"
    SUBSTACK = "substack"
    UNKNOWN = "unknown"


class DataOrchestrator:
    """Main orchestrator for data collection workflow"""
    
    def __init__(self):
        self.logger = get_logger("orchestrator")
        self.stats = {
            'total_sources': 0,
            'sources_processed': 0,
            'total_articles': 0,
            'new_articles': 0,
            'cached_articles': 0,
            'errors': 0
        }
    
    def detect_source_type(self, source_url: str) -> str:
        """
        Detect the type of source based on URL patterns.
        
        Args:
            source_url: URL or handle to classify
            
        Returns:
            Source type constant
        """
        source_url = source_url.strip().lower()
        
        if 'x.com' in source_url or 'twitter.com' in source_url:
            return SourceType.TWITTER
        elif 'substack.com' in source_url:
            return SourceType.SUBSTACK
        elif any(rss_indicator in source_url for rss_indicator in 
                 ['rss', 'feed', 'atom', '.xml']):
            return SourceType.RSS
        elif any(news_site in source_url for news_site in 
                 ['nytimes.com', 'theguardian.com', 'bbc', 'theverge.com', 'ycombinator.com']):
            return SourceType.RSS
        else:
            self.logger.warning(f"Could not determine source type for: {source_url}")
            return SourceType.UNKNOWN
    
    def parse_sources_from_file(self, file_path: str) -> List[str]:
        """
        Parse sources from a text file.
        
        Args:
            file_path: Path to sources file
            
        Returns:
            List of source URLs/handles
        """
        self.logger.info(f"Reading sources from file: {file_path}")
        
        try:
            with open(file_path, 'r') as f:
                sources = []
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        sources.append(line)
                
                self.logger.info(f"Found {len(sources)} sources in file")
                return sources
                
        except FileNotFoundError:
            self.logger.error(f"Sources file not found: {file_path}")
            raise
        except Exception as e:
            self.logger.error(f"Error reading sources file: {str(e)}")
            raise
    
    def parse_sources_from_string(self, sources_string: str) -> List[str]:
        """
        Parse sources from comma-separated string.
        
        Args:
            sources_string: Comma-separated URLs/handles
            
        Returns:
            List of source URLs/handles
        """
        sources = [s.strip() for s in sources_string.split(',') if s.strip()]
        self.logger.info(f"Parsed {len(sources)} sources from input string")
        return sources
    
    @log_performance
    def process_source(self, source_url: str, days_back: int = 7) -> Dict[str, Any]:
        """
        Process a single source: detect type, check cache, scrape if needed.
        
        Args:
            source_url: Source URL or handle
            days_back: How many days back to look for articles
            
        Returns:
            Dictionary with results and metadata
        """
        self.logger.info(f"Processing source: {source_url}")
        
        source_type = self.detect_source_type(source_url)
        
        result = {
            'source_url': source_url,
            'source_type': source_type,
            'articles': [],
            'new_count': 0,
            'cached_count': 0,
            'error': None,
            'processing_time': 0
        }
        
        start_time = datetime.now()
        
        try:
            # Check existing data in database first
            existing_articles, needs_scraping = check_and_scrape(
                source_url, source_type, days_back
            )
            
            if not needs_scraping and existing_articles:
                # Use cached data
                result['articles'] = existing_articles
                result['cached_count'] = len(existing_articles)
                self.stats['cached_articles'] += len(existing_articles)
                self.logger.info(f"Using {len(existing_articles)} cached articles for {source_url}")
            
            else:
                # Need to scrape new data
                self.logger.info(f"Scraping fresh data for {source_url}")
                
                if source_type == SourceType.TWITTER:
                    scrape_result = scrape_twitter(source_url, days_back)
                    
                elif source_type == SourceType.SUBSTACK:
                    scrape_result = scrape_substack_research(source_url, days_back)
                    
                elif source_type == SourceType.RSS:
                    scrape_result = scrape_blog_or_rss(source_url, days_back)
                    
                else:
                    raise ValueError(f"Unsupported source type: {source_type}")
                
                # Process scraping results
                new_articles = scrape_result.get('results', [])
                
                if new_articles:
            
                    inserted_count = scrape_result.get('new_count', 0)  # Use new_count from scraper
                    
                    result['articles'] = new_articles
                    result['new_count'] = inserted_count
                    self.stats['new_articles'] += inserted_count
                    
                    self.logger.info(f"Processed {len(new_articles)} total articles from {source_url} ({inserted_count} new, {len(new_articles) - inserted_count} cached)")
                else:
                    self.logger.info(f"No articles found for {source_url}")
            
            self.stats['sources_processed'] += 1
            
        except Exception as e:
            error_msg = f"Error processing {source_url}: {str(e)}"
            self.logger.error(error_msg)
            result['error'] = error_msg
            self.stats['errors'] += 1
        
        result['processing_time'] = (datetime.now() - start_time).total_seconds()
        self.stats['total_articles'] += len(result['articles'])
        
        return result
    
    def format_articles_for_db(self, articles: List[Dict], source_type: str, source_url: str) -> List[Dict[str, Any]]:
        """
        Convert scraped articles to database format.
        
        Args:
            articles: List of scraped articles
            source_type: Type of source
            source_url: Source URL to use for all articles
            
        Returns:
            List of articles formatted for database insertion
        """
        db_articles = []
        
        for article in articles:
            published_date = None
            if article.get('published'):
                if isinstance(article['published'], str):
                    published_date = datetime.fromisoformat(article['published'].replace('Z', '+00:00'))
                else:
                    published_date = article['published']
            
            db_article = {
                'source_type': source_type,
                'source_url': source_url,  
                'title': article.get('title'),
                'content': article.get('content', ''),
                'link': article.get('link'),
                'published_date': published_date or datetime.utcnow()
            }
            
            db_articles.append(db_article)
        
        return db_articles
    
    @log_performance
    def process_all_sources(self, sources: List[str], days_back: int = 7) -> Dict[str, Any]:
        """
        Process all sources and return consolidated results.
        
        Args:
            sources: List of source URLs/handles
            days_back: How many days back to look for articles
            
        Returns:
            Dictionary with all results and statistics
        """
        self.logger.info(f"Starting processing of {len(sources)} sources")
        
        self.stats['total_sources'] = len(sources)
        results = []
        
        for i, source in enumerate(sources, 1):
            self.logger.info(f"Processing source {i}/{len(sources)}: {source}")
            
            source_result = self.process_source(source, days_back)
            results.append(source_result)
            
            # Log progress
            if i % 5 == 0 or i == len(sources):
                self.logger.info(f"Progress: {i}/{len(sources)} sources processed")
        
        # Generate final statistics
        final_result = {
            'success': True,
            'sources': results,
            'statistics': self.stats,
            'summary': {
                'total_sources': self.stats['total_sources'],
                'successful_sources': self.stats['sources_processed'],
                'failed_sources': self.stats['errors'],
                'total_articles': self.stats['total_articles'],
                'new_articles': self.stats['new_articles'],
                'cached_articles': self.stats['cached_articles']
            },
            'timestamp': datetime.utcnow().isoformat()
        }
        
        self.logger.info("=== Processing Complete ===")
        self.logger.info(f"Sources processed: {self.stats['sources_processed']}/{self.stats['total_sources']}")
        self.logger.info(f"Total articles: {self.stats['total_articles']}")
        self.logger.info(f"New articles: {self.stats['new_articles']}")
        self.logger.info(f"Cached articles: {self.stats['cached_articles']}")
        self.logger.info(f"Errors: {self.stats['errors']}")
        
        return final_result


def interactive_mode():
    """Interactive mode for testing and manual data collection"""
    print("\\n=== TrendMind Data Collector - Interactive Mode ===")
    
    orchestrator = DataOrchestrator()
    
    while True:
        print("\\nOptions:")
        print("1. Process sources from file")
        print("2. Process single source")
        print("3. View database statistics")
        print("4. Exit")
        
        choice = input("\\nEnter your choice (1-4): ").strip()
        
        if choice == '1':
            file_path = input("Enter sources file path (default: data/sources.txt): ").strip()
            if not file_path:
                file_path = "data/sources.txt"
            
            try:
                sources = orchestrator.parse_sources_from_file(file_path)
                days_back = int(input("Days back to search (default: 7): ") or "7")
                
                result = orchestrator.process_all_sources(sources, days_back)
                print(f"\\nProcessing complete! Check logs for details.")
                print(f"Summary: {result['summary']}")
                
            except Exception as e:
                print(f"Error: {e}")
        
        elif choice == '2':
            source_url = input("Enter source URL or handle: ").strip()
            if source_url:
                days_back = int(input("Days back to search (default: 7): ") or "7")
                
                result = orchestrator.process_source(source_url, days_back)
                print(f"\\nResult: {result}")
        
        elif choice == '3':
            try:
                counts = get_article_count_by_source(days_back=30)
                print("\\nDatabase Statistics (last 30 days):")
                for source, count in counts.items():
                    print(f"  {source}: {count} articles")
            except Exception as e:
                print(f"Error fetching statistics: {e}")
        
        elif choice == '4':
            print("Goodbye!")
            break
        
        else:
            print("Invalid choice. Please try again.")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='TrendMind Data Collection Orchestrator',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--sources-file', 
        help='Path to sources file (default: data/sources.txt)',
        default='data/sources.txt'
    )
    
    parser.add_argument(
        '--sources',
        help='Comma-separated list of source URLs/handles'
    )
    
    parser.add_argument(
        '--days-back',
        type=int,
        default=7,
        help='Number of days back to search for articles (default: 7)'
    )
    
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Run in interactive mode'
    )
    
    parser.add_argument(
        '--output',
        help='Output file for results (JSON format)'
    )
    
    args = parser.parse_args()
    
    if args.interactive:
        interactive_mode()
        return
    
    orchestrator = DataOrchestrator()
    
    # Determine source of URLs
    if args.sources:
        sources = orchestrator.parse_sources_from_string(args.sources)
    else:
        sources = orchestrator.parse_sources_from_file(args.sources_file)
    
    # Process all sources
    result = orchestrator.process_all_sources(sources, args.days_back)
    
    # Output results
    if args.output:
        import json
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"Results saved to: {args.output}")
    
    # Print summary
    print("\\n" + "="*50)
    print("DATA COLLECTION SUMMARY")
    print("="*50)
    summary = result['summary']
    print(f"Sources processed: {summary['successful_sources']}/{summary['total_sources']}")
    print(f"Total articles: {summary['total_articles']}")
    print(f"New articles: {summary['new_articles']}")
    print(f"Cached articles: {summary['cached_articles']}")
    
    if summary['failed_sources'] > 0:
        print(f"Failed sources: {summary['failed_sources']}")
    
    return result


if __name__ == "__main__":
    main()