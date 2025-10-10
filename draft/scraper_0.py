import feedparser
from newspaper import Article
from datetime import datetime, timedelta, timezone
import re
import requests
import os
import json
import time
from dotenv import load_dotenv, find_dotenv
from src.db_postgres import connect_postgres, insert_posts
from pathlib import Path
from utils.logger import get_logger, log_performance, log_scraping_metrics
import logging
from typing import Dict, Any, List
from bs4 import BeautifulSoup

load_dotenv(find_dotenv())
BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

@log_performance
def scrape_blog_or_rss(url: str, days_back: int = 30, save_path: str = "blog_posts.json"):
    """Scrape RSS/blog content and save to JSON file."""
    logger = get_logger("scraper")
    logger.info(f"Starting RSS/blog scraping for: {url}")
    
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    logger.debug(f"Using cutoff date: {cutoff}")
    
    feed = feedparser.parse(url)
    results = []
    errors = []

    # Load existing posts if file exists
    file_path = Path(save_path)
    if file_path.exists():
        logger.debug(f"Loading existing posts from {save_path}")
        with open(save_path, "r", encoding="utf-8") as f:
            existing_posts = json.load(f)
        logger.info(f"Found {len(existing_posts)} existing posts")
    else:
        logger.info("No existing posts file found, starting fresh")
        existing_posts = []

    if not feed.entries:
        error_msg = "No entries found in feed"
        logger.warning(f"{error_msg} for {url}")
        return {"results": [], "error": error_msg}

    logger.info(f"Found {len(feed.entries)} entries in feed")
    entries_processed = 0
    
    for entry in feed.entries:
        entries_processed += 1
        try:
            published = datetime(*entry.published_parsed[:6])
            if published < cutoff:
                logger.debug(f"Skipping old entry: {entry.title} ({published})")
                continue
                
            logger.debug(f"Processing entry: {entry.title}")
            article = Article(entry.link)
            article.download()
            article.parse()
            
            post_entry = {
                "source": url,
                "title": article.title,
                "content": article.text,
                "published": published.isoformat()
            }
            
            # Avoid duplicates
            if post_entry not in existing_posts:
                existing_posts.append(post_entry)
                results.append(post_entry)
            else:
                logger.debug("Duplicate post found, skipping")
            
        except Exception as e:
            error_msg = f"Error processing entry {entry.link}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

    # Save updated posts back to JSON
    logger.debug(f"Saving {len(existing_posts)} total posts to {save_path}")
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(existing_posts, f, ensure_ascii=False, indent=4)

    logger.info(f"Added {len(results)} new posts to {save_path} (total now: {len(existing_posts)})")

    # Log scraping metrics
    log_scraping_metrics(url, results, errors)
    
    return {"results": results}

@log_performance
def scrape_substack_research(urls: List[str] = None,
                             days_back: int = 30,
                             save_path: str = "substack_research.json") -> Dict[str, Any]:
    """
    Scrape Substack research posts (full text) and save to JSON file.
    """
    logger = get_logger("scraper")

    if urls is None:
        urls = [
            "https://garymarcus.substack.com/feed",
            "https://andrewng.substack.com/feed"
        ]

    logger.info(f"Starting Substack scraping for: {urls}")
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    logger.debug(f"Using cutoff date: {cutoff}")

    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    file_path = Path(save_path)
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            existing_posts = json.load(f)
        logger.info(f"Loaded {len(existing_posts)} existing posts")
    else:
        logger.info("No existing posts file found, starting fresh")
        existing_posts = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/127.0.0.1 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    for url in urls:
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

                    link = entry.link
                    title = entry.title

                    # Fetch full post
                    response = requests.get(link, headers=headers, timeout=15)
                    response.raise_for_status()

                    soup = BeautifulSoup(response.text, "html.parser")
                    article_tag = soup.find("article") or soup.find("div", {"role": "main"})
                    if article_tag:
                        paragraphs = [p.get_text(strip=True) for p in article_tag.find_all("p")]
                        full_content = "\n".join(paragraphs).strip()
                    else:
                        full_content = entry.get("summary", "")

                    post_entry = {
                        "source": url,
                        "title": title,
                        "link": link,
                        "content": full_content,
                        "published": published.isoformat() if published else None
                    }

                    if post_entry not in existing_posts:
                        existing_posts.append(post_entry)
                        results.append(post_entry)
                        logger.debug(f"Added new post: {title}")

                except Exception as e:
                    err_msg = f"Error processing entry {entry.get('link')}: {e}"
                    logger.error(err_msg)
                    errors.append(err_msg)

        except Exception as e:
            err_msg = f"Error fetching feed {url}: {e}"
            logger.error(err_msg)
            errors.append(err_msg)

    # Save combined results
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(existing_posts, f, ensure_ascii=False, indent=4)

    logger.info(f"Scraping complete. Added {len(results)} new posts. Total: {len(existing_posts)}")

    log_scraping_metrics(", ".join(urls), results, errors)

    return {"results": results, "errors": errors}

@log_performance
def scrape_twitter(handle: str, days_back: int = 7, save_path: str = "tweets.json"):
    """Scrape tweets from a public Twitter handle once and append to JSON safely."""
    logger = get_logger("scraper")
    
    clean_handle = handle.replace("https://x.com/", "").replace("@", "").strip("/")
    logger.info(f"Starting Twitter scraping for handle: {clean_handle}")
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    logger.debug(f"Using cutoff date: {cutoff}")
    
    tweets = []
    errors = []
    max_results = 10

    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
    params = {
        "query": f"from:{clean_handle} -is:retweet -is:reply",
        "max_results": max_results,
        "tweet.fields": "created_at,text"
    }

    # Load existing tweets if file exists
    file_path = Path(save_path)
    if file_path.exists():
        logger.debug(f"Loading existing tweets from {save_path}")
        with open(save_path, "r", encoding="utf-8") as f:
            existing_tweets = json.load(f)
        logger.info(f"Found {len(existing_tweets)} existing tweets")
    else:
        logger.info("No existing tweet file found, starting fresh")
        existing_tweets = []

    try:
        logger.debug("Making API request to Twitter")
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 429:
            reset_time = int(response.headers.get("x-rate-limit-reset", time.time() + 60))
            wait_seconds = max(reset_time - int(time.time()), 1)
            logger.warning(f"Rate limit hit. Waiting {wait_seconds} seconds...")
            time.sleep(wait_seconds)
            response = requests.get(url, headers=headers, params=params)

        response.raise_for_status()
        data = response.json()

        tweets_in_response = len(data.get("data", []))
        logger.info(f"Received {tweets_in_response} tweets from API")

        for tweet in data.get("data", []):
            try:
                tweet_date = datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00"))
                if tweet_date < cutoff:
                    logger.debug(f"Skipping old tweet from {tweet_date}")
                    continue

                clean_text = re.sub(r"http\S+", "", tweet["text"]).strip()
                tweet_entry = {
                    "source": f"https://x.com/{clean_handle}",
                    "title": None,
                    "content": clean_text,
                    "published": tweet_date.isoformat()
                }

                # Avoid duplicates
                if tweet_entry not in existing_tweets:
                    existing_tweets.append(tweet_entry)
                    tweets.append(tweet_entry)
                else:
                    logger.debug("Duplicate tweet found, skipping")
                    
            except Exception as e:
                error_msg = f"Error processing tweet: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Save updated tweets back to JSON
        logger.debug(f"Saving {len(existing_tweets)} total tweets to {save_path}")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(existing_tweets, f, ensure_ascii=False, indent=4)

        logger.info(f"Added {len(tweets)} new tweets to {save_path} (total now: {len(existing_tweets)})")
        
        # Log scraping metrics
        log_scraping_metrics(f"https://x.com/{clean_handle}", tweets, errors)
        
        return {"results": tweets}

    except requests.RequestException as e:
        error_msg = f"Error fetching tweets: {e}"
        logger.error(error_msg)
        errors.append(error_msg)
        log_scraping_metrics(f"https://x.com/{clean_handle}", [], errors)
        return {"results": []}

@log_performance
def scrape_source(url_or_handle: str):
    """Auto-detect source type and scrape accordingly."""
    logger = get_logger("scraper")
    
    if "x.com" in url_or_handle or "twitter.com" in url_or_handle:
        logger.info(f"Detected Twitter source: {url_or_handle}")
        return scrape_twitter(url_or_handle)
    else:
        logger.info(f"Detected RSS/blog source: {url_or_handle}")
        return scrape_blog_or_rss(url_or_handle)
