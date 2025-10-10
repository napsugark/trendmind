import sys
import os
from src.scraper import scrape_blog_or_rss, scrape_twitter, scrape_substack_research
from dotenv import load_dotenv, find_dotenv

if __name__ == "__main__":
    load_dotenv(find_dotenv())
    # # print(os.getenv("TWITTER_BEARER_TOKEN"))
    # posts = scrape_blog_or_rss("https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml")
  
    # # # posts = list(scrape_source(url))
    # print(posts)

        # posts = scrape_blog_or_rss("https://www.theguardian.com/uk/technology/rss")
        # print(posts)

    # posts = scrape_blog_or_rss("https://feeds.bbci.co.uk/news/technology/rss.xml")
    # # print(posts)

    # posts = scrape_blog_or_rss("https://www.theverge.com/rss/tech/index.xml")

    # posts = scrape_blog_or_rss("https://news.ycombinator.com/rss")


    # substack = scrape_substack_research()
    # print(substack)
    
    # tweets = scrape_twitter("sama", days_back=7)
    # print(tweets)

    # sources = [
    # "https://x.com/karpathy",
    # "https://garymarcus.substack.com/feed",
    # "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"
    # ]

    # all_articles = []

    # for source in sources:
    #     result = scrape_source(source, days_back=7)
        
    #     print(f"Source: {source}")
    #     print(f"  - New articles: {result.get('new_count', 0)}")
    #     print(f"  - Cached articles: {result.get('cached_count', 0)}")
    #     print(f"  - Total: {len(result['results'])}")
        
    #     all_articles.extend(result['results'])

    # print(f"\nTotal articles collected: {len(all_articles)}")

