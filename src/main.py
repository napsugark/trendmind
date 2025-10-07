import os
from dotenv import load_dotenv
from langfuse import observe
from langfuse.decorators import langfuse_context
from scraper import scrape_source
from summarizer import summarize_posts
from db_postgres import connect_postgres, insert_posts
from db_qdrant import embed_and_store

@observe()
def load_sources():
    """Load and return source URLs from the configuration file."""
    with open("data/sources.txt", "r") as f:
        sources = [line.strip() for line in f if line.strip()]
    
    # Log metadata to Langfuse
    langfuse_context.update_current_observation(
        metadata={"sources_count": len(sources), "sources": sources}
    )
    
    return sources

@observe()
def scrape_all_sources(sources):
    """Scrape content from all configured sources."""
    all_posts = []
    
    for i, src in enumerate(sources):
        print(f"Scraping: {src}")
        
        # Create a span for each source scraping
        with langfuse_context.observation(name=f"scrape_source_{i+1}") as observation:
            observation.update(
                input={"source": src},
                metadata={"source_index": i+1, "total_sources": len(sources)}
            )
            
            posts = scrape_source(src)
            all_posts.extend(posts)
            
            observation.update(
                output={"posts_collected": len(posts)},
                metadata={"cumulative_posts": len(all_posts)}
            )
    
    # Update observation with final results
    langfuse_context.update_current_observation(
        output={"total_posts": len(all_posts)},
        metadata={"posts_per_source": {src: len([p for p in all_posts if p.get("source") == src]) for src in sources}}
    )
    
    return all_posts

@observe()
def store_data(all_posts):
    """Store collected posts in both PostgreSQL and Qdrant."""
    # Store in PostgreSQL
    with langfuse_context.observation(name="store_postgres") as observation:
        observation.update(input={"posts_count": len(all_posts)})
        conn = connect_postgres()
        insert_posts(conn, all_posts)
        observation.update(output={"status": "success"})

    # Store embeddings in Qdrant
    with langfuse_context.observation(name="store_qdrant") as observation:
        observation.update(input={"posts_count": len(all_posts)})
        embed_and_store(all_posts)
        observation.update(output={"status": "success"})

@observe()
def main():
    """Main pipeline for TrendMind: scrape, store, and summarize AI trend data."""
    load_dotenv()
    
    # Set session metadata for the entire run
    langfuse_context.update_current_trace(
        name="trendmind_pipeline",
        metadata={"pipeline_version": "1.0", "run_type": "scheduled"}
    )

    # Load sources
    sources = load_sources()
    print(f"Loaded {len(sources)} sources")

    # Scrape all sources
    all_posts = scrape_all_sources(sources)
    print(f"Collected {len(all_posts)} posts")

    # Store data
    store_data(all_posts)

    # Summarize
    summary = summarize_posts(all_posts)
    print("\n===== Monthly Digest =====\n")
    print(summary)
    
    # Update trace with final results
    langfuse_context.update_current_trace(
        output={"summary_length": len(summary) if summary else 0},
        metadata={"total_posts_processed": len(all_posts)}
    )

if __name__ == "__main__":
    main()
