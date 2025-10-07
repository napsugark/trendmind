import os
from openai import AzureOpenAI
from langfuse import observe
from langfuse.openai import AsyncAzureOpenAI
import asyncio

# Initialize Azure OpenAI client with Langfuse tracing
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION")
)

@observe()
def summarize_posts(posts):
    """
    Summarize collected posts into a monthly digest using Azure OpenAI.
    This function is traced by Langfuse for observability.
    """
    if not posts:
        return None

    # Prepare content for summarization
    combined_text = "\n\n".join(p["content"] for p in posts if p["content"])
    
    # Log input metadata to Langfuse
    print(f"Summarizing {len(posts)} posts, combined length: {len(combined_text)} chars")
    
    prompt = (
        "Summarize the following text into a concise monthly digest. "
        "Highlight the main AI topics, insights, and emerging trends.\n\n"
        f"{combined_text[:12000]}"
    )

    # This call will be automatically traced by Langfuse
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
    
    # Log summary metadata
    print(f"Generated summary length: {len(summary)} chars")
    
    return summary
