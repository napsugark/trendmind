import os
from openai import AzureOpenAI
from langfuse import observe, Langfuse
from utils.logger import get_logger, log_performance, log_summary_metrics
from typing import List, Dict, Any

# Initialize clients
from langfuse.openai import openai

client = openai.AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION")
)
langfuse = Langfuse()

@observe()
@log_performance
def summarize_single_cluster(cluster: Dict[str, Any], cluster_index: int) -> Dict[str, Any]:
    """
    Generate summary for a single cluster of articles.
    Each cluster gets its own Langfuse trace for individual evaluation.
    
    Args:
        cluster: Single cluster dictionary from clustering.py
        cluster_index: Index of the cluster (for naming/logging)
        
    Returns:
        Dictionary with cluster summary
    """
    logger = get_logger("summarizer")
    topic_name = cluster.get('topic_name', f'Topic {cluster_index+1}')
    logger.info(f"Summarizing cluster {cluster_index+1}: {topic_name}")
    
    try:
        # Prepare content from cluster articles
        articles_text = []
        sources = set()
        
        for article in cluster.get('articles', []):
            if article.get('content'):
                articles_text.append(f"Title: {article.get('title', 'No title')}\nContent: {article['content'][:500]}")
            # Prefer 'link' over 'source_url' when available
            source = article.get('link') or article.get('source_url')
            if source:
                sources.add(source)
        
        combined_text = "\n\n".join(articles_text[:10])  # Limit to 10 articles per cluster
        
        # Get prompt from Langfuse with fallback
        try:
            prompt_template = langfuse.get_prompt("trendmind-cluster-summary-prompt", label="latest")
            prompt = prompt_template.compile(
                topic_name=topic_name,
                combined_text=combined_text[:8000]
            )
            logger.debug(f"Using Langfuse cluster summary prompt version: {prompt_template.version}")
        except Exception as e:
            logger.warning(f"Failed to fetch Langfuse cluster summary prompt, using fallback: {e}")
            # Fallback to hardcoded prompt
            prompt = f"""
            Analyze the following articles about "{topic_name}" and provide a concise summary in bullet points.
            
            Articles:
            {combined_text[:8000]}
            
            Format your response as 3-4 bullet points that highlight:
            • Main themes and developments
            • Key insights or findings  
            • Important trends or implications
            • Notable companies, products, or technologies mentioned
            
            Use clear, informative bullet points that capture the essence of these articles.
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
        summary = content.strip() if content else "Summary not available"
        
        cluster_summary = {
            'topic_name': topic_name,
            'article_count': len(cluster.get('articles', [])),
            'summary': summary,
            'sources': list(sources)
        }
        
        logger.info(f"Generated summary for cluster: {topic_name}")
        return cluster_summary
        
    except Exception as e:
        logger.error(f"Error summarizing cluster {cluster_index+1}: {str(e)}")
        # Check for Azure OpenAI content filter error
        if "ResponsibleAIPolicyViolation" in str(e):
            summary = "Summary not available due to content policy restrictions."
        else:
            summary = "Summary generation failed."
        
        return {
            'topic_name': topic_name,
            'article_count': len(cluster.get('articles', [])),
            'summary': summary,
            'sources': list(sources) if 'sources' in locals() else []
        }


@log_performance  # Remove @observe() from the parent function
def summarize_clusters(clusters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate summaries for each cluster of articles.
    Each cluster gets its own Langfuse trace for individual evaluation.
    
    Args:
        clusters: List of cluster dictionaries from clustering.py
        
    Returns:
        List of cluster summaries with topic_name, summary, sources, etc.
    """
    logger = get_logger("summarizer")
    logger.info(f"Summarizing {len(clusters)} clusters")
    
    cluster_summaries = []
    
    # Process each cluster with individual tracing
    for i, cluster in enumerate(clusters):
        cluster_summary = summarize_single_cluster(cluster, i)
        cluster_summaries.append(cluster_summary)
    
    logger.info(f"Completed summarization of {len(cluster_summaries)} clusters")
    return cluster_summaries
