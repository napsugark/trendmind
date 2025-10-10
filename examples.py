#!/usr/bin/env python3
"""
TrendMind Usage Examples

This script demonstrates various ways to use the TrendMind data collection system.
"""

import os
import sys
import json
from datetime import datetime

# Add current directory to path
sys.path.append(os.path.dirname(__file__))

from get_data import DataOrchestrator
from src.db_postgres import get_article_count_by_source

def example_1_sources_file():
    """Example 1: Process sources from file"""
    print("\\n" + "="*50)
    print("EXAMPLE 1: Processing sources from file")
    print("="*50)
    
    orchestrator = DataOrchestrator()
    
    try:
        # Load sources from file
        sources = orchestrator.parse_sources_from_file('data/sources.txt')
        print(f"Found {len(sources)} sources in file")
        
        # Process all sources
        result = orchestrator.process_all_sources(sources, days_back=3)
        
        # Print summary
        summary = result['summary']
        print(f"\\nResults:")
        print(f"- Sources processed: {summary['successful_sources']}/{summary['total_sources']}")
        print(f"- Total articles: {summary['total_articles']}")
        print(f"- New articles: {summary['new_articles']}")
        print(f"- Cached articles: {summary['cached_articles']}")
        
        return result
        
    except Exception as e:
        print(f"Error: {e}")
        return None

def example_2_single_source():
    """Example 2: Process a single source"""
    print("\\n" + "="*50)
    print("EXAMPLE 2: Processing single source")
    print("="*50)
    
    orchestrator = DataOrchestrator()
    
    # Test with a reliable RSS feed
    source = "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"
    
    try:
        result = orchestrator.process_source(source, days_back=7)
        
        print(f"Source: {result['source_url']}")
        print(f"Type: {result['source_type']}")
        print(f"Articles found: {len(result['articles'])}")
        print(f"New articles: {result['new_count']}")
        print(f"Cached articles: {result['cached_count']}")
        print(f"Processing time: {result['processing_time']:.2f}s")
        
        if result['error']:
            print(f"Error: {result['error']}")
        
        return result
        
    except Exception as e:
        print(f"Error: {e}")
        return None

def example_3_multiple_sources():
    """Example 3: Process multiple sources programmatically"""
    print("\\n" + "="*50)
    print("EXAMPLE 3: Processing multiple sources")
    print("="*50)
    
    orchestrator = DataOrchestrator()
    
    # Mix of different source types
    sources = [
        "https://garymarcus.substack.com/",
        "https://x.com/karpathy",
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"
    ]
    
    try:
        result = orchestrator.process_all_sources(sources, days_back=5)
        
        print(f"Processed {len(sources)} sources:")
        
        for source_result in result['sources']:
            print(f"\\n- {source_result['source_url']} ({source_result['source_type']})")
            print(f"  Articles: {len(source_result['articles'])}")
            print(f"  New: {source_result['new_count']}, Cached: {source_result['cached_count']}")
            
            if source_result['error']:
                print(f"  Error: {source_result['error']}")
        
        return result
        
    except Exception as e:
        print(f"Error: {e}")
        return None

def example_4_database_stats():
    """Example 4: View database statistics"""
    print("\\n" + "="*50)
    print("EXAMPLE 4: Database statistics")
    print("="*50)
    
    try:
        # Get stats for different time periods
        stats_7d = get_article_count_by_source(7)
        stats_30d = get_article_count_by_source(30)
        
        print("Articles by source (last 7 days):")
        if stats_7d:
            for source, count in stats_7d.items():
                print(f"  {source}: {count}")
        else:
            print("  No articles found")
        
        print(f"\\nTotal articles (7 days): {sum(stats_7d.values()) if stats_7d else 0}")
        print(f"Total articles (30 days): {sum(stats_30d.values()) if stats_30d else 0}")
        
    except Exception as e:
        print(f"Error: {e}")

def example_5_api_format():
    """Example 5: Show API-like usage"""
    print("\\n" + "="*50)
    print("EXAMPLE 5: API-style usage")
    print("="*50)
    
    orchestrator = DataOrchestrator()
    
    # Simulate API request
    api_request = {
        "sources": [
            "https://x.com/sama",
            "https://andrewng.substack.com/"
        ],
        "days_back": 3
    }
    
    try:
        result = orchestrator.process_all_sources(
            api_request["sources"], 
            api_request["days_back"]
        )
        
        # Show JSON-like output
        api_response = {
            "success": result["success"],
            "timestamp": result["timestamp"],
            "summary": result["summary"],
            "sources": [
                {
                    "url": s["source_url"],
                    "type": s["source_type"],
                    "article_count": len(s["articles"]),
                    "new_articles": s["new_count"],
                    "processing_time": s["processing_time"]
                }
                for s in result["sources"]
            ]
        }
        
        print("API Response:")
        print(json.dumps(api_response, indent=2))
        
        return api_response
        
    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    """Run all examples"""
    print("TrendMind Data Collection Examples")
    print("Make sure your database is running and configured!")
    
    # Run examples
    example_4_database_stats()  # Start with DB stats
    
    # example_1_sources_file()
    # example_2_single_source() 
    # example_3_multiple_sources()
    # example_5_api_format()
    
    print("\\n" + "="*50)
    print("All examples completed!")
    print("="*50)
    print("\\nNext steps:")
    print("1. Run: python get_data.py --interactive")
    print("2. Or run: python frontend.py  (then visit http://localhost:5000)")
    print("3. Or use get_data.py with command line arguments")

if __name__ == "__main__":
    main()