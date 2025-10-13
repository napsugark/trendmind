

# # Step 1: Cluster the articles
# clusters = cluster_articles(articles)
# print("\n--- CLUSTERS ---")
# for c in clusters:
#     print(f"{c['topic_name']} ({c['article_count']} articles)")

# # Step 2: Summarize each cluster
# summaries = [summarize_cluster(c) for c in clusters]
# print("\n--- SUMMARIES ---")
# for s in summaries:
#     print(f"\n{s['topic_name']}\n{s['summary'][:300]}...")

# # Step 3: Generate final overview
# overview = generate_final_overview(summaries)
# print("\n--- FINAL OVERVIEW ---\n")
# print(overview)
# Standard library
import os
from typing import List, Dict, Any
# Load environment variables
from dotenv import load_dotenv, find_dotenv
# Langfuse
from langfuse import Langfuse, observe
# Azure OpenAI client
from openai import AzureOpenAI
# Your utility functions
from backend.utils.logger import get_logger, log_performance
# Import your clustering functions
from backend.src.clustering import cluster_articles, summarize_cluster, generate_final_overview
from backend.src.db_postgres import connect_postgres  
import psycopg2.extras


if __name__ == "__main__":
    load_dotenv(find_dotenv())

    logger = get_logger("llm_test")
    logger.info("Starting LLM test script")
    # articles = [
    # {
    #     "title": "OpenAI launches GPT-5",
    #     "content": "OpenAI has released GPT-5 with major reasoning upgrades.",
    #     "source_url": "https://openai.com/blog/gpt-5"
    # },
    # {
    #     "title": "Google DeepMind advances in robotics",
    #     "content": "DeepMind unveils a new robotic learning framework that improves motion efficiency.",
    #     "source_url": "https://deepmind.com/news/robotics"
    # },
    # {
    #     "title": "AI regulation heats up in Europe",
    #     "content": "The EU proposes stricter AI laws affecting generative models.",
    #     "source_url": "https://bbc.com/news/ai-eu-law"
    # }
    # ]   
    # clusters = cluster_articles(articles)
    # summaries = [summarize_cluster(c) for c in clusters]
    # overview = generate_final_overview(summaries)
    # print(overview)
    try:
        # Connect to the database
        conn = connect_postgres()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Fetch the latest 10 articles
        cursor.execute("""
            SELECT id, source_type, source_url, title, content, link, published_date
            FROM articles
            ORDER BY published_date DESC
            LIMIT 10
        """)
        latest_articles = cursor.fetchall()
        cursor.close()
        conn.close()

        if not latest_articles:
            logger.warning("No articles found in the database.")
            exit(0)

        # Transform to the format expected by cluster_articles
        articles = [
            {
                "title": a.get("title"),
                "content": a.get("content"),
                "source_url": a.get("source_url")
            }
            for a in latest_articles
        ]

        # Run clustering and summarization
        clusters = cluster_articles(articles)
        summaries = [summarize_cluster(c) for c in clusters]
        overview = generate_final_overview(summaries)

        print(overview)
        logger.info("LLM clustering and summarization completed successfully.")

    except Exception as e:
        logger.error(f"Error running LLM test script: {e}")
