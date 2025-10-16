import os
from openai import AzureOpenAI
from langfuse import observe, Langfuse
from typing import List, Dict, Any
import json
from utils.logger import get_logger, log_performance
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# Initialize clients
client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)
langfuse = Langfuse()
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")


@observe()
@log_performance
def filter_ai_relevant_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter articles to keep only those that are relevant to AI, machine learning, 
    artificial intelligence, or related technologies.
    
    Args:
        articles: List of article dictionaries with 'title', 'content', 'source_url'
        
    Returns:
        List of filtered articles that are AI-relevant
    """
    logger = get_logger("content_filter")
    logger.info(f"Starting AI relevance filtering for {len(articles)} articles")
    
    if not articles:
        return articles
    
    # Prepare articles for batch processing (process in chunks to avoid token limits)
    chunk_size = 20  # Process 20 articles at a time
    filtered_articles = []
    
    for i in range(0, len(articles), chunk_size):
        chunk = articles[i:i + chunk_size]
        logger.debug(f"Processing chunk {i//chunk_size + 1}: articles {i+1}-{min(i+chunk_size, len(articles))}")
        
        # Prepare article summaries for filtering
        article_summaries = []
        for idx, article in enumerate(chunk):
            summary = {
                "id": i + idx,
                "title": article.get('title', 'No Title'),
                "snippet": article.get('content', '')[:300]  # First 300 chars
            }
            article_summaries.append(summary)
        
        # Get prompt from Langfuse with fallback
        try:
            prompt_template = langfuse.get_prompt("trendmind-ai-filter-prompt", label="latest")
            prompt = prompt_template.compile(
                articles_json=json.dumps(article_summaries, indent=2)
            )
            logger.debug(f"Using Langfuse AI filter prompt version: {prompt_template.version}")
        except Exception as e:
            logger.warning(f"Failed to fetch Langfuse AI filter prompt, using fallback: {e}")
            # Fallback to hardcoded prompt
            prompt = f"""You are an expert at identifying AI-related content. Review these articles and determine which ones are relevant to artificial intelligence, machine learning, automation, or related technologies.

Articles to evaluate:
{json.dumps(article_summaries, indent=2)}

Return a JSON object with ONLY the IDs of articles that are AI-related:
{{
  "ai_relevant_ids": [0, 2, 5, 7]
}}

AI-related topics include:
- Artificial Intelligence, Machine Learning, Deep Learning
- AI applications (healthcare AI, autonomous vehicles, etc.)
- AI ethics, regulation, governance
- AI companies, startups, funding
- AI research, models, algorithms
- Automation and robotics
- Natural language processing, computer vision
- AI tools and platforms

Exclude articles about:
- General technology without AI focus
- Politics/economics unless directly about AI policy
- Entertainment unless about AI in media/gaming
- Sports, lifestyle, travel, etc.
"""

        try:
            logger.debug("Sending AI filtering request to LLM")
            
            response = client.chat.completions.create(
                model=DEPLOYMENT,
                messages=[
                    {"role": "system", "content": "You are an expert at identifying AI-related content. Be precise and only include articles that genuinely discuss AI technologies."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for consistent classification
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            relevant_ids = set(result.get("ai_relevant_ids", []))
            
            logger.debug(f"LLM identified {len(relevant_ids)} AI-relevant articles out of {len(chunk)}")
            
            # Add relevant articles from this chunk
            for idx, article in enumerate(chunk):
                global_idx = i + idx
                if global_idx in relevant_ids:
                    filtered_articles.append(article)
                    logger.debug(f"Kept article: {article.get('title', 'No Title')[:50]}...")
                else:
                    logger.debug(f"Filtered out: {article.get('title', 'No Title')[:50]}...")
            
        except Exception as e:
            logger.error(f"AI filtering failed for chunk {i//chunk_size + 1}: {str(e)}")
            logger.warning("Using fallback: keeping all articles in this chunk")
            filtered_articles.extend(chunk)
    
    logger.info(f"AI relevance filtering complete: {len(filtered_articles)} relevant articles out of {len(articles)} total ({len(filtered_articles)/len(articles)*100:.1f}%)")
    
    return filtered_articles


@observe()
@log_performance  
def quick_ai_keyword_filter(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fast keyword-based pre-filter to remove obviously non-AI articles.
    This is a cheaper first pass before the LLM-based filtering.
    
    Args:
        articles: List of article dictionaries
        
    Returns:
        List of articles that passed the keyword filter
    """
    logger = get_logger("content_filter")
    logger.info(f"Starting keyword pre-filtering for {len(articles)} articles")
    
    # AI-related keywords (case insensitive)
    ai_keywords = {
        'artificial intelligence', 'machine learning', 'deep learning', 'neural network',
        'ai', 'ml', 'llm', 'gpt', 'chatgpt', 'openai', 'anthropic', 'claude',
        'automation', 'algorithm', 'model', 'training', 'inference', 'embedding',
        'computer vision', 'nlp', 'natural language', 'robotics', 'autonomous',
        'generative', 'transformer', 'diffusion', 'stable diffusion', 'midjourney',
        'langchain', 'hugging face', 'tensorflow', 'pytorch', 'scikit-learn',
        'recommendation system', 'predictive', 'classification', 'regression',
        'supervised', 'unsupervised', 'reinforcement learning', 'gan', 'vae'
    }
    
    filtered_articles = []
    
    for article in articles:
        title = article.get('title', '').lower()
        content = article.get('content', '').lower()
        combined_text = f"{title} {content}"
        
        # Check if any AI keyword is present
        has_ai_keyword = any(keyword in combined_text for keyword in ai_keywords)
        
        if has_ai_keyword:
            filtered_articles.append(article)
            logger.debug(f"Keyword match: {article.get('title', 'No Title')[:50]}...")
        else:
            logger.debug(f"No AI keywords: {article.get('title', 'No Title')[:50]}...")
    
    logger.info(f"Keyword filtering complete: {len(filtered_articles)} articles passed out of {len(articles)} total ({len(filtered_articles)/len(articles)*100:.1f}%)")
    
    return filtered_articles