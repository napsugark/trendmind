import os
from openai import AzureOpenAI
from langfuse import observe, Langfuse
from typing import List, Dict, Any
import json
from utils.logger import get_logger, log_performance
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# Initialize clients
from langfuse.openai import openai

client = openai.AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)
langfuse = Langfuse()
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")


@observe()
@log_performance  
def summarize_single_article(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a concise summary for a single article.
    
    Args:
        article: Article dictionary with 'title', 'content', etc.
        
    Returns:
        Dictionary with original article data plus 'ai_summary' field
    """
    logger = get_logger("clustering")
    
    # Make a copy to avoid modifying the original
    article_copy = article.copy()
    
    title = article.get('title', 'No Title')
    content = article.get('content', '')[:1000]  # First 1000 chars
    
    if not content:
        # If no content, just return article with title as summary
        article_copy['ai_summary'] = title
        return article_copy
    
    prompt = f"""Summarize this AI-related article in 2-3 sentences. Focus on the key AI concepts, developments, or implications.

Title: {title}
Content: {content}

Provide a concise summary that captures the main AI-related points."""

    try:
        response = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are an expert at summarizing AI news articles concisely."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150  # Keep summaries short
        )
        
        summary = response.choices[0].message.content.strip()
        article_copy['ai_summary'] = summary
        
        return article_copy
        
    except Exception as e:
        logger.warning(f"Failed to summarize article '{title[:50]}...': {str(e)}")
        # Fallback to title + first sentence of content
        first_sentence = content.split('.')[0] if content else ""
        article_copy['ai_summary'] = f"{title}. {first_sentence}" if first_sentence else title
        return article_copy


@observe()
@log_performance
def summarize_articles_batch(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Summarize multiple articles, with each getting its own Langfuse trace.
    
    Args:
        articles: List of article dictionaries
        
    Returns:
        List of articles with 'ai_summary' field added
    """
    logger = get_logger("clustering")
    logger.info(f"Summarizing {len(articles)} articles individually")
    
    summarized_articles = []
    for i, article in enumerate(articles):
        try:
            summarized_article = summarize_single_article(article)
            summarized_articles.append(summarized_article)
            
            if (i + 1) % 10 == 0:  # Log progress every 10 articles
                logger.info(f"Summarized {i + 1}/{len(articles)} articles")
                
        except Exception as e:
            logger.error(f"Error summarizing article {i}: {str(e)}")
            # Add article without summary
            article['ai_summary'] = article.get('title', 'No Title')
            summarized_articles.append(article)
    
    logger.info(f"Completed summarizing {len(summarized_articles)} articles")
    return summarized_articles


@observe()
@log_performance
def cluster_articles(articles: List[Dict[str, Any]], max_clusters: int = 2) -> List[Dict[str, Any]]:
    """
    Use LLM to cluster articles by topic using their AI summaries.
    
    Args:
        articles: List of article dictionaries with 'ai_summary' field (from summarize_articles_batch)
        max_clusters: Maximum number of clusters to create
        
    Returns:
        List of cluster dictionaries, each containing:
            - topic_name: Name of the topic
            - articles: List of articles in this cluster
            - article_count: Number of articles
    """
    logger = get_logger("clustering")
    logger.info(f"Starting clustering of {len(articles)} articles using AI summaries")
    
    # Prepare article summaries for clustering using the AI summaries
    article_summaries = []
    for i, article in enumerate(articles):
        summary = {
            "array_index": i,
            "title": article.get('title', 'No Title'),
            "ai_summary": article.get('ai_summary', 'No summary available'),
            "source": article.get('link') or article.get('source_url', 'Unknown')
        }
        article_summaries.append(summary)
    
    logger.info(f"Prepared {len(article_summaries)} article summaries for clustering")
    logger.debug(f"Articles JSON length: {len(json.dumps(article_summaries, indent=1))} characters")
    
    # Debug: Check if articles have ai_summary
    articles_with_summary = sum(1 for a in articles if a.get('ai_summary'))
    logger.info(f"Articles with ai_summary: {articles_with_summary}/{len(articles)}")
    
    # Debug: Log first few summaries
    for i in range(min(3, len(article_summaries))):
        summary_preview = article_summaries[i]['ai_summary'][:100] + "..." if len(article_summaries[i]['ai_summary']) > 100 else article_summaries[i]['ai_summary']
        logger.debug(f"Article {i} summary: {summary_preview}")
    
    # Get prompt from Langfuse with enhanced fallback
    try:
        prompt_template = langfuse.get_prompt("trendmind-clustering-prompt", label="latest")  # Latest version
        prompt = prompt_template.compile(
            num_articles=len(articles),
            max_clusters=max_clusters,
            articles_json=json.dumps(article_summaries, indent=2)
        )
        logger.debug(f"Using Langfuse prompt version: {prompt_template.version}")
        
        # ENHANCED: Add validation reminder to any Langfuse prompt
        prompt += f"""

MANDATORY VALIDATION REMINDER:
- You have {len(articles)} articles (array_index 0 to {len(articles)-1})
- EVERY article must be assigned to a cluster
- Count your article_ids before responding to ensure they total {len(articles)}
- Missing articles will cause the clustering to fail validation
"""
        
    except Exception as e:
        logger.warning(f"Failed to fetch Langfuse prompt, using enhanced fallback: {e}")
                # Fallback to hardcoded prompt
        prompt = f"""You are analyzing AI news articles. Group these {len(articles)} articles into 2-{max_clusters} meaningful topic clusters based on their AI summaries and themes.

Articles to cluster (MUST analyze ALL {len(articles)} articles):
{json.dumps(article_summaries, indent=1)}

Return a JSON object with this structure:
{{
  "clusters": [
    {{
      "topic_name": "Brief topic name",
      "description": "One sentence describing this topic",
      "article_ids": [0, 5, 12]  // Use ONLY the "array_index" values (0 to {len(articles)-1})
    }},
    {{
      "topic_name": "Another topic",
      "description": "One sentence describing this other topic", 
      "article_ids": [1, 3, 7]  // Different array_index values
    }}
  ]
}}

MANDATORY REQUIREMENTS - FAILURE TO FOLLOW WILL BE REJECTED:
1. EVERY SINGLE ARTICLE MUST BE ASSIGNED: You have {len(articles)} articles with array_index from 0 to {len(articles)-1}
2. COMPLETE COVERAGE: Your article_ids across all clusters must include EVERY number from 0 to {len(articles)-1}
3. NO MISSING ARTICLES: If any article_ids are missing, the clustering is INVALID
4. VERIFICATION STEP: Before responding, count your article_ids to ensure they total exactly {len(articles)} and cover 0 to {len(articles)-1}

CLUSTERING STRATEGY:
- Start by reviewing ALL {len(articles)} summaries carefully
- Identify 2-{max_clusters} main themes/topics across the summaries  
- Assign EVERY article to the most appropriate cluster
- If an article doesn't fit well, put it in the closest thematic match
- Common AI topics: Healthcare AI, AI Ethics/Regulation, AI Business/Investment, AI Tools/Products, AI Research/Models, AI Art/Entertainment, AI Security/Safety, AI Infrastructure

QUALITY CHECKS:
- Each cluster should have meaningful thematic coherence
- Topic names should be concise (2-5 words)
- Each cluster should ideally have 3+ articles (but assign all articles regardless)
- Balance cluster sizes when possible

FINAL VERIFICATION BEFORE RESPONDING:
1. Count total article_ids across all clusters = {len(articles)} ✓
2. Check all numbers 0 to {len(articles)-1} are included ✓
3. No article appears in multiple clusters ✓
4. All clusters have meaningful topic names ✓

If verification fails, revise your clustering until all {len(articles)} articles are properly assigned.
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
        logger.info(f"Full LLM response: {response.choices[0].message.content}")  # Log full response to debug
        
        # Build cluster objects with actual articles
        clusters = []
        total_clustered_articles = 0
        
        for cluster_info in clusters_data:
            article_ids = cluster_info.get("article_ids", [])
            logger.info(f"Cluster '{cluster_info.get('topic_name', 'Unknown')}' has article IDs: {article_ids}")
            
            # Validate article IDs and get valid articles
            valid_article_ids = [i for i in article_ids if isinstance(i, int) and 0 <= i < len(articles)]
            invalid_ids = [i for i in article_ids if not (isinstance(i, int) and 0 <= i < len(articles))]
            
            if invalid_ids:
                logger.warning(f"Invalid article IDs found in cluster '{cluster_info.get('topic_name')}': {invalid_ids}")
            
            cluster_articles = [articles[i] for i in valid_article_ids]
            total_clustered_articles += len(cluster_articles)
            
            cluster = {
                "topic_name": cluster_info.get("topic_name", "Unknown Topic"),
                "description": cluster_info.get("description", ""),
                "articles": cluster_articles,
                "article_count": len(cluster_articles)
            }
            clusters.append(cluster)
            
            logger.info(f"Cluster '{cluster['topic_name']}': {cluster['article_count']} articles (IDs: {valid_article_ids})")
        
        logger.info(f"Total articles clustered: {total_clustered_articles} out of {len(articles)} input articles")
        
        # ENHANCED: Check for missed articles and redistribute them
        all_clustered_ids = set()
        for cluster_info in clusters_data:
            article_ids = cluster_info.get("article_ids", [])
            all_clustered_ids.update([i for i in article_ids if isinstance(i, int) and 0 <= i < len(articles)])
        
        missed_ids = set(range(len(articles))) - all_clustered_ids
        if missed_ids:
            logger.warning(f"LLM missed {len(missed_ids)} articles (IDs: {sorted(missed_ids)}). Redistributing intelligently...")
            
            # Strategy: Distribute missed articles to existing clusters based on similarity
            if clusters and len(missed_ids) <= len(articles) // 2:  # If not too many missed
                # Distribute evenly across existing clusters
                missed_list = list(missed_ids)
                for i, missed_id in enumerate(missed_list):
                    target_cluster = i % len(clusters_data)
                    clusters_data[target_cluster]["article_ids"].append(missed_id)
                    logger.debug(f"Added missed article {missed_id} to cluster '{clusters_data[target_cluster]['topic_name']}'")
                
                # Rebuild clusters with redistributed articles
                clusters = []
                for cluster_info in clusters_data:
                    article_ids = cluster_info.get("article_ids", [])
                    valid_article_ids = [i for i in article_ids if isinstance(i, int) and 0 <= i < len(articles)]
                    cluster_articles = [articles[i] for i in valid_article_ids]
                    
                    cluster = {
                        "topic_name": cluster_info.get("topic_name", "Unknown Topic"),
                        "description": cluster_info.get("description", ""),
                        "articles": cluster_articles,
                        "article_count": len(cluster_articles)
                    }
                    clusters.append(cluster)
                    logger.info(f"Redistributed cluster '{cluster['topic_name']}': {cluster['article_count']} articles")
                
            else:
                # Too many missed articles - create separate cluster
                missed_articles = [articles[i] for i in missed_ids]
                clusters.append({
                    "topic_name": "Additional AI Topics",
                    "description": "Additional articles that required separate clustering",
                    "articles": missed_articles,
                    "article_count": len(missed_articles)
                })
                logger.info(f"Created 'Additional AI Topics' cluster with {len(missed_articles)} missed articles")
        
        # Final verification
        total_clustered = sum(cluster['article_count'] for cluster in clusters)
        if total_clustered != len(articles):
            logger.error(f"CLUSTERING VALIDATION FAILED: {total_clustered} clustered != {len(articles)} input articles")
        else:
            logger.info(f"CLUSTERING VALIDATION PASSED: All {len(articles)} articles successfully clustered")
        
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
        f"Source: {a.get('link') or a.get('source_url', 'Unknown')}\n"
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
        
        # Extract unique sources - prefer 'link' over 'source_url'
        sources = list(set(a.get('link') or a.get('source_url', 'Unknown') for a in articles))
        
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


# @observe()
# @log_performance
# def generate_final_overview(cluster_summaries: List[Dict[str, Any]], top_n: int = 5) -> str:
#     """
#     Generate final overview of top N trending topics.
    
#     Args:
#         cluster_summaries: List of cluster summary dictionaries
#         top_n: Number of top topics to include
        
#     Returns:
#         Formatted string with top trending topics
#     """
#     logger = get_logger("clustering")
#     logger.info(f"Generating final overview of top {top_n} topics from {len(cluster_summaries)} clusters")
    
#     # Sort by article count to get top trending
#     sorted_clusters = sorted(cluster_summaries, key=lambda x: x['article_count'], reverse=True)
#     top_clusters = sorted_clusters[:top_n]
    
#     # Prepare input for LLM
#     cluster_info = []
#     for i, cluster in enumerate(top_clusters):
#         cluster_info.append({
#             "rank": i + 1,
#             "topic": cluster['topic_name'],
#             "articles": cluster['article_count'],
#             "summary": cluster['summary'],
#             "sources": cluster.get('key_sources', [])[:3]
#         })
    
#     prompt = f"""Create a final overview of the top {top_n} trending AI topics based on the following cluster summaries:

# {json.dumps(cluster_info, indent=2)}

# Format the output as:

# **Overview**
# [2-3 sentence overview of the overall landscape]

# **Top {top_n} Trending Topics:**

# 1. **[Topic Name]** ({len} articles)
#    [3-4 sentence summary]
   
#    Key sources: [list sources]

# 2. **[Topic Name]** ({len} articles)
#    ...

# Make it engaging and insightful. Highlight connections between topics if relevant."""

#     try:
#         logger.debug("Generating final overview")
        
#         response = client.chat.completions.create(
#             model=DEPLOYMENT,
#             messages=[
#                 {"role": "system", "content": "You are an expert at synthesizing AI news trends into clear, compelling narratives."},
#                 {"role": "user", "content": prompt}
#             ],
#             temperature=0.7,
#             max_tokens=1500
#         )
        
#         overview = response.choices[0].message.content
        
#         logger.info(f"Generated final overview: {len(overview)} chars")
        
#         return overview
        
#     except Exception as e:
#         logger.error(f"Failed to generate final overview: {str(e)}")
        
#         # Fallback: simple formatting
#         fallback = f"**Top {top_n} Trending AI Topics**\n\n"
#         for i, cluster in enumerate(top_clusters):
#             fallback += f"{i+1}. **{cluster['topic_name']}** ({cluster['article_count']} articles)\n"
#             fallback += f"   {cluster['summary'][:200]}...\n\n"
        
#         return fallback