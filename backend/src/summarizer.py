import os
from openai import AzureOpenAI
from langfuse import observe, Langfuse
from utils.logger import get_logger, log_performance, log_summary_metrics
from typing import List, Dict, Any

# Initialize clients
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION")
)
langfuse = Langfuse()

@observe()
@log_performance
def summarize_posts(posts):
    """
    Summarize collected posts into a monthly digest using Azure OpenAI.
    This function is traced by Langfuse for observability.
    """
    logger = get_logger("summarizer")
    
    if not posts:
        logger.warning("No posts provided for summarization")
        return None

    logger.info(f"Starting summarization of {len(posts)} posts")
    
    # Prepare content for summarization
    combined_text = "\n\n".join(p["content"] for p in posts if p["content"])
    
    logger.info(f"Combined text length: {len(combined_text)} characters")
    logger.debug(f"Text will be truncated to 12000 characters for processing")
    
    # Get prompt from Langfuse with fallback
    try:
        prompt_template = langfuse.get_prompt("trendmind-monthly-digest-prompt", version=None)
        prompt = prompt_template.compile(
            combined_text=combined_text[:12000]
        )
        logger.debug(f"Using Langfuse monthly digest prompt version: {prompt_template.version}")
    except Exception as e:
        logger.warning(f"Failed to fetch Langfuse monthly digest prompt, using fallback: {e}")
        # Fallback to hardcoded prompt
        prompt = (
            "Summarize the following text into a concise monthly digest. "
            "Highlight the main AI topics, insights, and emerging trends.\n\n"
            f"{combined_text[:12000]}"
        )

    try:
        # This call will be automatically traced by Langfuse
        logger.debug("Sending request to Azure OpenAI for summarization")
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            messages=[
                {"role": "system", "content": "You are an expert summarizer in AI trends."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1500,
            temperature=0.7
        )
        
        summary = response.choices[0].message.content
        tokens_used = response.usage.total_tokens
        
        logger.info(f"Successfully generated summary: {len(summary)} characters")
        logger.info(f"Tokens used: {tokens_used}")
        
        # Log detailed metrics
        log_summary_metrics(
            input_posts=len(posts),
            summary_length=len(summary),
            tokens_used=tokens_used,
            cost_estimate=tokens_used * 0.00002  # Rough estimate for GPT-4
        )
        
        return summary
        
    except Exception as e:
        logger.error(f"Failed to generate summary: {str(e)}")
        raise

@observe()
@log_performance
def summarize_clusters(clusters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate summaries for each cluster of articles.
    
    Args:
        clusters: List of cluster dictionaries from clustering.py
        
    Returns:
        List of cluster summaries with topic_name, summary, key_points, etc.
    """
    logger = get_logger("summarizer")
    logger.info(f"Summarizing {len(clusters)} clusters")
    
    cluster_summaries = []
    
    for i, cluster in enumerate(clusters):
        logger.info(f"Processing cluster {i+1}: {cluster.get('topic_name', 'Unknown')}")
        
        try:
            # Prepare content from cluster articles
            articles_text = []
            sources = set()
            
            for article in cluster.get('articles', []):
                if article.get('content'):
                    articles_text.append(f"Title: {article.get('title', 'No title')}\nContent: {article['content'][:500]}")
                if article.get('source_url'):
                    sources.add(article['source_url'])
            
            combined_text = "\n\n".join(articles_text[:10])  # Limit to 10 articles per cluster
            
            # Get prompt from Langfuse with fallback
            try:
                prompt_template = langfuse.get_prompt("trendmind-cluster-summary-prompt", version=None)
                prompt = prompt_template.compile(
                    topic_name=cluster.get('topic_name', 'this topic'),
                    combined_text=combined_text[:8000]
                )
                logger.debug(f"Using Langfuse cluster summary prompt version: {prompt_template.version}")
            except Exception as e:
                logger.warning(f"Failed to fetch Langfuse cluster summary prompt, using fallback: {e}")
                # Fallback to hardcoded prompt
                prompt = f"""
                Analyze the following articles about "{cluster.get('topic_name', 'this topic')}" and provide:
                1. A concise summary (2-3 sentences)
                2. Key insights and trends (3-5 bullet points)
                
                Articles:
                {combined_text[:8000]}
                
                Please format your response as:
                SUMMARY: [your summary here]
                KEY_POINTS: [bullet point 1] | [bullet point 2] | [bullet point 3] | etc.
                """
            
            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
                messages=[
                    {"role": "system", "content": "You are an expert AI trend analyst. Provide clear, concise summaries."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=800,
                temperature=0.3
            )
            
            content = response.choices[0].message.content
            
            # Parse response
            summary = ""
            key_points = []
            
            lines = content.split('\n')
            for line in lines:
                if line.startswith('SUMMARY:'):
                    summary = line.replace('SUMMARY:', '').strip()
                elif line.startswith('KEY_POINTS:'):
                    points_text = line.replace('KEY_POINTS:', '').strip()
                    key_points = [p.strip() for p in points_text.split('|') if p.strip()]
            
            # Fallback if parsing fails
            if not summary:
                summary = content.split('\n')[0] if content else "Summary not available"
            if not key_points:
                key_points = ["Key insights not available"]
            
            cluster_summary = {
                'topic_name': cluster.get('topic_name', f'Topic {i+1}'),
                'article_count': len(cluster.get('articles', [])),
                'summary': summary,
                'key_points': key_points,
                'sources': list(sources)
            }
            
            cluster_summaries.append(cluster_summary)
            logger.info(f"Generated summary for cluster: {cluster_summary['topic_name']}")
            
        except Exception as e:
            logger.error(f"Error summarizing cluster {i+1}: {str(e)}")
            # Add fallback summary
            cluster_summaries.append({
                'topic_name': cluster.get('topic_name', f'Topic {i+1}'),
                'article_count': len(cluster.get('articles', [])),
                'summary': 'Summary generation failed',
                'key_points': ['Unable to generate insights'],
                'sources': list(sources) if 'sources' in locals() else []
            })
    
    logger.info(f"Completed summarization of {len(cluster_summaries)} clusters")
    return cluster_summaries
