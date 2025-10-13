import os
from openai import AzureOpenAI
from langfuse import observe
from typing import List, Dict, Any
import json
from backend.utils.logger import get_logger, log_performance
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# Initialize Azure OpenAI client
client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")


@observe()
@log_performance
def cluster_articles(articles: List[Dict[str, Any]], max_clusters: int = 5) -> List[Dict[str, Any]]:
    """
    Use LLM to cluster articles by topic.
    
    Args:
        articles: List of article dictionaries with 'title', 'content', 'source_url'
        max_clusters: Maximum number of clusters to create
        
    Returns:
        List of cluster dictionaries, each containing:
            - topic_name: Name of the topic
            - articles: List of articles in this cluster
            - article_count: Number of articles
    """
    logger = get_logger("clustering")
    logger.info(f"Starting clustering of {len(articles)} articles")
    
    # Prepare article summaries for clustering
    article_summaries = []
    for i, article in enumerate(articles):
        summary = {
            "id": i,
            "title": article.get('title', 'No Title'),
            "source": article.get('source_url', 'Unknown'),
            "snippet": article.get('content', '')[:200]  # First 200 chars
        }
        article_summaries.append(summary)
    
    prompt = f"""You are analyzing articles from various AI news sources. Group these {len(articles)} articles into 5-{max_clusters} coherent topic clusters.

Articles to cluster:
{json.dumps(article_summaries, indent=2)}

Return a JSON object with this structure:
{{
  "clusters": [
    {{
      "topic_name": "Brief topic name",
      "description": "One sentence describing this topic",
      "article_ids": [0, 5, 12]  // IDs of articles in this cluster
    }}
  ]
}}

Rules:
- Each article should belong to exactly one cluster
- Topic names should be concise (2-5 words)
- Aim for 5-8 clusters depending on topic diversity
- Group by semantic similarity, not just keywords
"""

    try:
        logger.debug("Sending clustering request to LLM")
        
        response = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are an expert at identifying topics and clustering related content."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # Lower temperature for more consistent clustering
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        clusters_data = result.get("clusters", [])
        
        logger.info(f"LLM identified {len(clusters_data)} clusters")
        
        # Build cluster objects with actual articles
        clusters = []
        for cluster_info in clusters_data:
            article_ids = cluster_info.get("article_ids", [])
            cluster_articles = [articles[i] for i in article_ids if i < len(articles)]
            
            cluster = {
                "topic_name": cluster_info.get("topic_name", "Unknown Topic"),
                "description": cluster_info.get("description", ""),
                "articles": cluster_articles,
                "article_count": len(cluster_articles)
            }
            clusters.append(cluster)
            
            logger.debug(f"Cluster '{cluster['topic_name']}': {cluster['article_count']} articles")
        
        # Sort by article count (most articles first)
        clusters.sort(key=lambda x: x['article_count'], reverse=True)
        
        return clusters
        
    except Exception as e:
        logger.error(f"Clustering failed: {str(e)}")
        # Fallback: create one cluster with all articles
        logger.warning("Using fallback: single cluster with all articles")
        return [{
            "topic_name": "AI News & Trends",
            "description": "General AI news and developments",
            "articles": articles,
            "article_count": len(articles)
        }]


@observe()
@log_performance
def summarize_cluster(cluster: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a detailed summary for a single topic cluster.
    
    Args:
        cluster: Cluster dictionary with 'topic_name', 'articles'
        
    Returns:
        Dictionary with:
            - topic_name: Topic name
            - article_count: Number of articles
            - summary: Generated summary text
            - key_sources: List of main sources
    """
    logger = get_logger("clustering")
    logger.info(f"Summarizing cluster: {cluster['topic_name']} ({cluster['article_count']} articles)")
    
    topic_name = cluster['topic_name']
    articles = cluster['articles']
    
    # Combine article content (limit to avoid token limits)
    combined_content = "\n\n---\n\n".join([
        f"Source: {a.get('source_url', 'Unknown')}\n"
        f"Title: {a.get('title', 'No Title')}\n"
        f"Content: {a.get('content', '')[:500]}"  # Limit each article
        for a in articles[:10]  # Max 10 articles per cluster
    ])
    
    prompt = f"""Summarize the following articles about "{topic_name}".

{combined_content}

Create a 3-paragraph summary that:
1. Explains what this topic is about
2. Highlights key developments, debates, or perspectives
3. Notes any contradictions or diverse viewpoints

Keep it concise but informative."""

    try:
        logger.debug(f"Generating summary for {topic_name}")
        
        response = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are an expert AI news analyst who creates insightful, balanced summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        summary_text = response.choices[0].message.content
        
        # Extract unique sources
        sources = list(set(a.get('source_url', 'Unknown') for a in articles))
        
        logger.info(f"Generated summary for {topic_name}: {len(summary_text)} chars")
        
        return {
            "topic_name": topic_name,
            "article_count": cluster['article_count'],
            "summary": summary_text,
            "key_sources": sources[:5]  # Top 5 sources
        }
        
    except Exception as e:
        logger.error(f"Failed to summarize cluster {topic_name}: {str(e)}")
        return {
            "topic_name": topic_name,
            "article_count": cluster['article_count'],
            "summary": f"Summary unavailable. This cluster contains {cluster['article_count']} articles about {topic_name}.",
            "key_sources": []
        }


@observe()
@log_performance
def generate_final_overview(cluster_summaries: List[Dict[str, Any]], top_n: int = 5) -> str:
    """
    Generate final overview of top N trending topics.
    
    Args:
        cluster_summaries: List of cluster summary dictionaries
        top_n: Number of top topics to include
        
    Returns:
        Formatted string with top trending topics
    """
    logger = get_logger("clustering")
    logger.info(f"Generating final overview of top {top_n} topics from {len(cluster_summaries)} clusters")
    
    # Sort by article count to get top trending
    sorted_clusters = sorted(cluster_summaries, key=lambda x: x['article_count'], reverse=True)
    top_clusters = sorted_clusters[:top_n]
    
    # Prepare input for LLM
    cluster_info = []
    for i, cluster in enumerate(top_clusters):
        cluster_info.append({
            "rank": i + 1,
            "topic": cluster['topic_name'],
            "articles": cluster['article_count'],
            "summary": cluster['summary'],
            "sources": cluster.get('key_sources', [])[:3]
        })
    
    prompt = f"""Create a final overview of the top {top_n} trending AI topics based on the following cluster summaries:

{json.dumps(cluster_info, indent=2)}

Format the output as:

**Overview**
[2-3 sentence overview of the overall landscape]

**Top {top_n} Trending Topics:**

1. **[Topic Name]** ({len} articles)
   [3-4 sentence summary]
   
   Key sources: [list sources]

2. **[Topic Name]** ({len} articles)
   ...

Make it engaging and insightful. Highlight connections between topics if relevant."""

    try:
        logger.debug("Generating final overview")
        
        response = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are an expert at synthesizing AI news trends into clear, compelling narratives."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1500
        )
        
        overview = response.choices[0].message.content
        
        logger.info(f"Generated final overview: {len(overview)} chars")
        
        return overview
        
    except Exception as e:
        logger.error(f"Failed to generate final overview: {str(e)}")
        
        # Fallback: simple formatting
        fallback = f"**Top {top_n} Trending AI Topics**\n\n"
        for i, cluster in enumerate(top_clusters):
            fallback += f"{i+1}. **{cluster['topic_name']}** ({cluster['article_count']} articles)\n"
            fallback += f"   {cluster['summary'][:200]}...\n\n"
        
        return fallback