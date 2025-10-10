import os
from openai import AzureOpenAI
from langfuse import observe
from langfuse.openai import AsyncAzureOpenAI
import asyncio
from logger import get_logger, log_performance, log_summary_metrics

# Initialize Azure OpenAI client with Langfuse tracing
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION")
)

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
