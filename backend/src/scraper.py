import feedparser
from newspaper import Article
from datetime import datetime, timedelta, timezone
import re
import requests
import os
import json
import time
from dotenv import load_dotenv, find_dotenv
from src.db_postgres import connect_postgres, insert_posts, get_existing_articles, article_exists
from pathlib import Path
from utils.logger import get_logger, log_performance, log_scraping_metrics
import logging
from typing import Dict, Any, List, Tuple
from bs4 import BeautifulSoup

load_dotenv(find_dotenv())
BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

def check_and_scrape(source_url: str, source_type: str, days_back: int) -> Tuple[List[Dict], bool]:
    """
    Check if we have sufficient data in DB. Returns (existing_articles, needs_scraping).
    
    Returns:
        - List of existing articles from DB
        - Boolean indicating if we need to scrape
    """
    logger = get_logger("scraper")
    
    cutoff_date = datetime.utcnow() - timedelta(days=days_back)
    
    # Get existing articles from DB
    existing = get_existing_articles(source_url, cutoff_date, datetime.utcnow())
    
    if not existing:
        logger.info(f"No cached data for {source_url}, will scrape")
        return [], True
    
    # Check if data is fresh (scraped within last 24 hours)
    latest_scrape = max(article['scraped_date'] for article in existing)
    hours_old = (datetime.utcnow() - latest_scrape).total_seconds() / 3600
    
    if hours_old > 24:
        logger.info(f"Cached data is {hours_old:.1f} hours old, will refresh")
        return existing, True
    
    logger.info(f"Using {len(existing)} cached articles from DB (scraped {hours_old:.1f}h ago)")
    return existing, False


@log_performance
def scrape_blog_or_rss(url: str, days_back: int = 30) -> Dict[str, Any]:
    """Scrape RSS/blog content and save to database."""
    logger = get_logger("scraper")
    
    # Strip URL to avoid whitespace issues
    url = url.strip()
    logger.info(f"Starting RSS/blog scraping for: {url}")
    
    # Check database first
    existing_articles, needs_scraping = check_and_scrape(url, 'rss', days_back)
    if not needs_scraping:
        logger.info(f"✓ Using {len(existing_articles)} cached articles from DB")
        return {"results": existing_articles, "from_cache": True}
    
    # Need to scrape fresh data
    logger.info(f"🕷️ Scraping fresh data from {url}")
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    
    feed = feedparser.parse(url)
    if not feed.entries:
        error_msg = "No entries found in feed"
        logger.warning(f"{error_msg} for {url}")
        return {"results": existing_articles, "error": error_msg}

    logger.info(f"Found {len(feed.entries)} entries in feed")
    
    new_articles = []
    errors = []

    # Open DB connection once
    conn = connect_postgres()
    cursor = conn.cursor()

    for entry in feed.entries:
        try:
            published = datetime(*entry.get("published_parsed", (0,0,0,0,0,0))[:6])
            if published < cutoff:
                continue
            
            # Skip if article exists
            if article_exists(cursor, url, published):
                logger.debug(f"Article already in DB: {entry.get('title', 'No Title')}")
                continue
            
            logger.debug(f"Processing new entry: {entry.get('title', 'No Title')}")
            
            article = Article(entry.get("link", ""))
            article.download()
            article.parse()
            
            article_data = {
                "source_type": "rss",
                "source_url": url,
                "title": article.title,
                "content": article.text,
                "link": entry.get("link", ""),
                "published_date": published
            }
            new_articles.append(article_data)
            
        except Exception as e:
            error_msg = f"Error processing entry {entry.get('link', 'Unknown')}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

    # Insert new articles to database
    if new_articles:
        insert_posts(new_articles, cursor=cursor, conn=conn)
        conn.commit()
        logger.info(f"✓ Inserted {len(new_articles)} new articles to DB")
    
    cursor.close()
    conn.close()
    
    all_articles = existing_articles + new_articles
    log_scraping_metrics(url, new_articles, errors)
    
    return {
        "results": all_articles,
        "new_count": len(new_articles),
        "cached_count": len(existing_articles),
        "from_cache": False
    }


@log_performance
def scrape_substack_research(urls: List[str] = None,
                             days_back: int = 30) -> Dict[str, Any]:
    """Scrape Substack research posts and save to database."""
    logger = get_logger("scraper")

    if urls is None:
        urls = [
            "https://garymarcus.substack.com/feed",
            "https://andrewng.substack.com/feed"
        ]

    logger.info(f"Starting Substack scraping for: {urls}")
    
    all_results = []
    total_new = 0
    total_cached = 0
    errors = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/127.0.0.1 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Open DB connection once for all URLs
    conn = connect_postgres()
    cursor = conn.cursor()

    for url in urls:
        existing_articles, needs_scraping = check_and_scrape(url, 'substack', days_back)
        
        if not needs_scraping:
            logger.info(f"✓ Using {len(existing_articles)} cached articles from DB for {url}")
            all_results.extend(existing_articles)
            total_cached += len(existing_articles)
            continue
        
        logger.info(f"🕷️ Scraping fresh data from {url}")
        cutoff = datetime.utcnow() - timedelta(days=days_back)
        new_articles = []

        try:
            feed = feedparser.parse(url)
            logger.info(f"Fetched feed: {url} with {len(feed.entries)} entries")

            for entry in feed.entries:
                try:
                    published = None
                    if hasattr(entry, "published_parsed"):
                        published = datetime(*entry.published_parsed[:6])
                    if published and published < cutoff:
                        continue

                    # Check if article already exists using existing cursor
                    if article_exists(cursor, url, published):
                        logger.debug(f"Article already in DB: {entry.title}")
                        continue

                    link = entry.link
                    title = entry.title

                    # Fetch full post content
                    response = requests.get(link, headers=headers, timeout=15)
                    response.raise_for_status()

                    soup = BeautifulSoup(response.text, "html.parser")
                    article_tag = soup.find("article") or soup.find("div", {"role": "main"})
                    if article_tag:
                        paragraphs = [p.get_text(strip=True) for p in article_tag.find_all("p")]
                        full_content = "\n".join(paragraphs).strip()
                    else:
                        full_content = entry.get("summary", "")

                    article_data = {
                        "source_type": "substack",
                        "source_url": url,
                        "title": title,
                        "content": full_content,
                        "link": link,
                        "published_date": published
                    }

                    new_articles.append(article_data)
                    logger.debug(f"Added new post: {title}")

                except Exception as e:
                    err_msg = f"Error processing entry {entry.get('link')}: {e}"
                    logger.error(err_msg)
                    errors.append(err_msg)

            # Insert new articles to DB
            if new_articles:
                insert_posts(new_articles, cursor=cursor, conn=conn)
                conn.commit()
                logger.info(f"✓ Inserted {len(new_articles)} new articles to DB")
                total_new += len(new_articles)

            # Combine existing + new
            all_results.extend(existing_articles + new_articles)

        except Exception as e:
            err_msg = f"Error fetching feed {url}: {e}"
            logger.error(err_msg)
            errors.append(err_msg)

    # Close connection at the very end
    cursor.close()
    conn.close()

    logger.info(f"Scraping complete. New: {total_new}, Cached: {total_cached}, Total: {len(all_results)}")
    log_scraping_metrics(", ".join(urls), [a for a in all_results if a.get('is_new')], errors)

    return {
        "results": all_results,
        "new_count": total_new,
        "cached_count": total_cached,
        "errors": errors
    }



@log_performance
def scrape_twitter(handle: str, days_back: int = 7) -> Dict[str, Any]:
    """Scrape tweets from a public Twitter handle and save to database."""
    logger = get_logger("scraper")
    
    # Clean handle and construct source URL
    clean_handle = handle.replace("https://x.com/", "").replace("@", "").strip("/")
    source_url = f"https://x.com/{clean_handle}"
    logger.info(f"Starting Twitter scraping for handle: {clean_handle}")

    # Check database first
    existing_tweets, needs_scraping = check_and_scrape(source_url, "twitter", days_back)
    if not needs_scraping:
        logger.info(f"✓ Using {len(existing_tweets)} cached tweets from DB")
        return {"results": existing_tweets, "from_cache": True}

    logger.info(f"🕷️ Scraping fresh tweets from {source_url}")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    logger.debug(f"Using cutoff date: {cutoff}")

    new_tweets: list[dict] = []
    errors: list[str] = []
    max_results = 10

    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
    params = {
        "query": f"from:{clean_handle} -is:retweet -is:reply",
        "max_results": max_results,
        "tweet.fields": "created_at,text"
    }

    try:
        logger.debug("Making API request to Twitter")
        response = requests.get(url, headers=headers, params=params)

        # Handle rate limit
        if response.status_code == 429:
            reset_time = int(response.headers.get("x-rate-limit-reset", time.time() + 60))
            wait_seconds = max(reset_time - int(time.time()), 1)
            logger.warning(f"Rate limit hit. Waiting {wait_seconds} seconds...")
            time.sleep(wait_seconds)
            response = requests.get(url, headers=headers, params=params)

        response.raise_for_status()
        tweets_data = response.json().get("data", [])
        logger.info(f"Received {len(tweets_data)} tweets from API")

        # Open DB connection once
        conn = connect_postgres()
        cursor = conn.cursor()

        for tweet in tweets_data:
            try:
                tweet_date = datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00"))
                if tweet_date < cutoff:
                    logger.debug(f"Skipping old tweet from {tweet_date}")
                    continue

                clean_text = re.sub(r"http\S+", "", tweet["text"]).strip()

                # Check only source + timestamp using existing cursor
                if article_exists(cursor, source_url, tweet_date):
                    logger.debug("Tweet already in DB, skipping")
                    continue

                new_tweets.append({
                    "source_type": "twitter",
                    "source_url": source_url,
                    "title": None,
                    "content": clean_text,
                    "link": None,
                    "published_date": tweet_date
                })

            except Exception as e:
                error_msg = f"Error processing tweet: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Insert all new tweets in one go
        if new_tweets:
            insert_posts(new_tweets, cursor=cursor, conn=conn)  # Pass cursor/conn to reuse
            logger.info(f"✓ Inserted {len(new_tweets)} new tweets to DB")

        cursor.close()
        conn.close()

    except requests.RequestException as e:
        error_msg = f"Error fetching tweets: {e}"
        logger.error(error_msg)
        errors.append(error_msg)

    all_tweets = existing_tweets + new_tweets
    log_scraping_metrics(source_url, new_tweets, errors)

    return {
        "results": all_tweets,
        "new_count": len(new_tweets),
        "cached_count": len(existing_tweets),
        "from_cache": False,
        "errors": errors
    }

@log_performance
def scrape_source(url_or_handle: str, days_back: int = 7) -> Dict[str, Any]:
    """Auto-detect source type and scrape accordingly."""
    logger = get_logger("scraper")
    
    if "x.com" in url_or_handle or "twitter.com" in url_or_handle:
        logger.info(f"Detected Twitter source: {url_or_handle}")
        return scrape_twitter(url_or_handle, days_back)
    elif "substack.com" in url_or_handle:
        logger.info(f"Detected Substack source: {url_or_handle}")
        return scrape_substack_research([url_or_handle], days_back)
    else:
        logger.info(f"Detected RSS/blog source: {url_or_handle}")
        return scrape_blog_or_rss(url_or_handle, days_back)