import feedparser
from newspaper import Article
import snscrape.modules.twitter as sntwitter
from datetime import datetime, timedelta
import re
from langfuse import observe
from langfuse.decorators import langfuse_context

@observe()
def scrape_blog_or_rss(url: str, days_back: int = 30):
    """Scrape RSS/blog content with Langfuse observability."""
    langfuse_context.update_current_observation(
        input={"url": url, "days_back": days_back},
        metadata={"scraper_type": "rss_blog"}
    )
    
    try:
        feed = feedparser.parse(url)
        results = []
        cutoff = datetime.utcnow() - timedelta(days=days_back)

        if not feed.entries:
            langfuse_context.update_current_observation(
                output={"results": [], "error": "No entries found in feed"},
                metadata={"feed_title": feed.feed.get("title", "Unknown")}
            )
            return results

        entries_processed = 0
        entries_included = 0

        for entry in feed.entries:
            entries_processed += 1
            
            try:
                published = datetime(*entry.published_parsed[:6])
                if published < cutoff:
                    continue
                    
                article = Article(entry.link)
                article.download()
                article.parse()
                
                results.append({
                    "source": url,
                    "title": article.title,
                    "content": article.text,
                    "published": published.isoformat()
                })
                entries_included += 1
                
            except Exception as e:
                print(f"Error processing entry {entry.link}: {e}")
        
        langfuse_context.update_current_observation(
            output={"results_count": len(results)},
            metadata={
                "feed_title": feed.feed.get("title", "Unknown"),
                "entries_processed": entries_processed,
                "entries_included": entries_included,
                "success_rate": entries_included / entries_processed if entries_processed > 0 else 0
            }
        )
        
        return results
        
    except Exception as e:
        langfuse_context.update_current_observation(
            output={"error": str(e)},
            level="ERROR"
        )
        print(f"Error scraping {url}: {e}")
        return []

@observe()
def scrape_twitter(handle: str, days_back: int = 30):
    """Scrape tweets from a public Twitter handle with observability."""
    clean_handle = handle.replace("https://x.com/", "").replace("@", "").strip("/")
    
    langfuse_context.update_current_observation(
        input={"handle": handle, "clean_handle": clean_handle, "days_back": days_back},
        metadata={"scraper_type": "twitter"}
    )
    
    try:
        cutoff = datetime.utcnow() - timedelta(days=days_back)
        tweets = []
        tweets_processed = 0

        for tweet in sntwitter.TwitterUserScraper(clean_handle).get_items():
            tweets_processed += 1
            
            if tweet.date < cutoff:
                break
                
            clean_text = re.sub(r"http\S+", "", tweet.content).strip()
            tweets.append({
                "source": f"https://x.com/{clean_handle}",
                "title": None,
                "content": clean_text,
                "published": tweet.date.isoformat()
            })
            
            # Limit to prevent excessive API usage
            if len(tweets) >= 100:
                break

        langfuse_context.update_current_observation(
            output={"results_count": len(tweets)},
            metadata={
                "tweets_processed": tweets_processed,
                "tweets_included": len(tweets),
                "handle": clean_handle
            }
        )
        
        return tweets
        
    except Exception as e:
        langfuse_context.update_current_observation(
            output={"error": str(e)},
            level="ERROR"
        )
        print(f"Error scraping Twitter handle {handle}: {e}")
        return []

@observe()
def scrape_source(url: str):
    """Auto-detect source type and scrape accordingly with observability."""
    source_type = "twitter" if ("x.com" in url or "twitter.com" in url) else "rss_blog"
    
    langfuse_context.update_current_observation(
        input={"url": url},
        metadata={"detected_source_type": source_type}
    )
    
    if source_type == "twitter":
        results = scrape_twitter(url)
    else:
        results = scrape_blog_or_rss(url)
    
    langfuse_context.update_current_observation(
        output={"results_count": len(results), "source_type": source_type}
    )
    
    return results
