import os
import json
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
import uuid

from content_filter import filter_ai_relevant_articles, quick_ai_keyword_filter
from utils.logger import get_logger

logger = get_logger("test_dataset")


def create_ai_filter_test_dataset(
    all_articles: List[Dict[str, Any]], 
    output_dir: str = "test_datasets",
    include_intermediate_steps: bool = True
) -> str:
    """
    Create a test dataset from article filtering results for Langfuse evaluation.
    
    Args:
        all_articles: List of all scraped articles before filtering
        output_dir: Directory to save the test dataset
        include_intermediate_steps: Whether to include keyword filtering step
        
    Returns:
        Path to the saved test dataset file
    """
    logger.info(f"Creating AI filter test dataset from {len(all_articles)} articles")
    
    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ai_filter_test_dataset_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    # Step 1: Keyword filtering (if requested)
    if include_intermediate_steps:
        keyword_filtered = quick_ai_keyword_filter(all_articles)
        logger.info(f"Keyword filter: {len(keyword_filtered)}/{len(all_articles)} articles passed")
    else:
        keyword_filtered = all_articles
    
    # Step 2: AI relevance filtering
    ai_filtered = filter_ai_relevant_articles(keyword_filtered)
    logger.info(f"AI filter: {len(ai_filtered)}/{len(keyword_filtered)} articles passed")
    
    # Create article lookup for easy matching
    def create_article_key(article):
        """Create unique key for article matching"""
        return f"{article.get('title', '')[:50]}_{article.get('source_url', '')}"
    
    # Build sets for fast lookup
    keyword_keys = {create_article_key(a) for a in keyword_filtered} if include_intermediate_steps else set()
    ai_keys = {create_article_key(a) for a in ai_filtered}
    
    # Create test dataset structure
    test_dataset = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "total_articles": len(all_articles),
            "keyword_filtered": len(keyword_filtered) if include_intermediate_steps else None,
            "ai_filtered": len(ai_filtered),
            "filter_accuracy": len(ai_filtered) / len(all_articles) if all_articles else 0,
            "description": "Test dataset for AI content filtering evaluation",
            "version": "1.0"
        },
        "test_cases": []
    }
    
    # Process each article
    for i, article in enumerate(all_articles):
        article_key = create_article_key(article)
        
        # Determine filtering results
        passed_keyword = article_key in keyword_keys if include_intermediate_steps else True
        passed_ai_filter = article_key in ai_keys
        
        # Create test case
        test_case = {
            "id": str(uuid.uuid4()),
            "article_id": i,
            "input": {
                "title": article.get('title', ''),
                "content": article.get('content', '')[:1000],  # Limit content for manageable size
                "source_url": article.get('source_url', ''),
                "source_type": article.get('source_type', ''),
                "published_date": article.get('published_date').isoformat() if article.get('published_date') else None,
                "link": article.get('link', '')
            },
            "filtering_results": {
                "passed_keyword_filter": passed_keyword if include_intermediate_steps else None,
                "passed_ai_filter": passed_ai_filter,
                "final_classification": "ai_relevant" if passed_ai_filter else "not_ai_relevant"
            },
            "ground_truth": {
                "is_ai_relevant": None,  # To be manually labeled
                "ai_categories": [],     # To be manually labeled (e.g., ["machine_learning", "ethics"])
                "confidence": None,      # To be manually labeled (1-5 scale)
                "notes": ""             # For manual annotation
            }
        }
        
        test_dataset["test_cases"].append(test_case)
    
    # Save to JSON file
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(test_dataset, f, indent=2, ensure_ascii=False, default=str)
    
    logger.info(f"Test dataset saved to: {filepath}")
    logger.info(f"Dataset contains {len(test_dataset['test_cases'])} test cases")
    
    # Create summary statistics
    ai_relevant_count = sum(1 for tc in test_dataset["test_cases"] if tc["filtering_results"]["passed_ai_filter"])
    logger.info(f"AI-relevant articles: {ai_relevant_count}/{len(all_articles)} ({ai_relevant_count/len(all_articles)*100:.1f}%)")
    
    return filepath


def create_langfuse_evaluation_dataset(test_dataset_path: str, output_path: str = None) -> str:
    """
    Convert test dataset to Langfuse evaluation format.
    
    Args:
        test_dataset_path: Path to the test dataset JSON file
        output_path: Optional custom output path
        
    Returns:
        Path to Langfuse evaluation dataset
    """
    logger.info(f"Converting test dataset to Langfuse format: {test_dataset_path}")
    
    # Load test dataset
    with open(test_dataset_path, 'r', encoding='utf-8') as f:
        test_dataset = json.load(f)
    
    # Generate output path if not provided
    if not output_path:
        base_name = Path(test_dataset_path).stem
        output_path = test_dataset_path.replace('.json', '_langfuse.json')
    
    # Convert to Langfuse evaluation format
    langfuse_dataset = {
        "name": "ai_content_filter_evaluation",
        "description": "Evaluation dataset for AI content filtering accuracy",
        "metadata": test_dataset["metadata"],
        "items": []
    }
    
    for test_case in test_dataset["test_cases"]:
        langfuse_item = {
            "id": test_case["id"],
            "input": {
                "article": {
                    "title": test_case["input"]["title"],
                    "content": test_case["input"]["content"],
                    "source": test_case["input"]["source_url"]
                }
            },
            "expected_output": {
                "is_ai_relevant": test_case["ground_truth"]["is_ai_relevant"],
                "categories": test_case["ground_truth"]["ai_categories"],
                "confidence": test_case["ground_truth"]["confidence"]
            },
            "actual_output": {
                "classification": test_case["filtering_results"]["final_classification"],
                "passed_filter": test_case["filtering_results"]["passed_ai_filter"]
            },
            "metadata": {
                "source_type": test_case["input"]["source_type"],
                "published_date": test_case["input"]["published_date"],
                "article_id": test_case["article_id"]
            }
        }
        
        langfuse_dataset["items"].append(langfuse_item)
    
    # Save Langfuse dataset
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(langfuse_dataset, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Langfuse evaluation dataset saved to: {output_path}")
    return output_path


def verify_langfuse_dataset(langfuse_dataset_path: str) -> bool:
    """
    Verify that the Langfuse evaluation dataset is correctly formatted.
    
    Args:
        langfuse_dataset_path: Path to the Langfuse evaluation dataset JSON file
        
    Returns:
        True if dataset is valid, False otherwise
    """
    try:
        with open(langfuse_dataset_path, 'r', encoding='utf-8') as f:
            dataset = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Error loading dataset: {e}")
        return False
    
    # Check required top-level fields
    required_fields = ["name", "description", "items"]
    for field in required_fields:
        if field not in dataset:
            print(f"❌ Missing required field: '{field}'")
            return False
    
    if not isinstance(dataset["items"], list):
        print("❌ 'items' field must be a list")
        return False
    
    if len(dataset["items"]) == 0:
        print("❌ Dataset contains no items")
        return False
    
    # Check format of individual items
    labeled_items = 0
    for i, item in enumerate(dataset["items"]):
        # Check required item fields
        required_item_fields = ["id", "input", "expected_output", "actual_output"]
        for field in required_item_fields:
            if field not in item:
                print(f"❌ Item {i}: Missing required field '{field}'")
                return False
        
        # Check if item has ground truth labels
        if item["expected_output"]["is_ai_relevant"] is not None:
            labeled_items += 1
        
        # Check input structure
        if "article" not in item["input"]:
            print(f"❌ Item {i}: Missing 'article' in input")
            return False
        
        article = item["input"]["article"]
        if not all(field in article for field in ["title", "content", "source"]):
            print(f"❌ Item {i}: Article missing required fields (title, content, source)")
            return False
    
    print(f"✅ Langfuse dataset is valid!")
    print(f"   - Total items: {len(dataset['items'])}")
    print(f"   - Labeled items: {labeled_items}")
    print(f"   - Unlabeled items: {len(dataset['items']) - labeled_items}")
    print(f"   - Dataset name: '{dataset['name']}'")
    
    if labeled_items == 0:
        print("⚠️  Warning: No items have ground truth labels (is_ai_relevant is null)")
        print("   You need to manually label some items before using for evaluation")
    
    return True


def calculate_evaluation_metrics(test_dataset_path: str) -> Dict[str, Any]:
    """
    Calculate precision, recall, F1-score and other metrics for the labeled dataset.
    
    Args:
        test_dataset_path: Path to the test dataset JSON file with ground truth labels
        
    Returns:
        Dictionary containing evaluation metrics
    """
    with open(test_dataset_path, 'r') as f:
        dataset = json.load(f)
    
    # Count true positives, false positives, etc.
    tp = fp = tn = fn = 0
    labeled_cases = 0
    
    for case in dataset["test_cases"]:
        ground_truth = case["ground_truth"]["is_ai_relevant"]
        if ground_truth is None:
            continue  # Skip unlabeled cases
            
        labeled_cases += 1
        predicted = case["filtering_results"]["passed_ai_filter"]
        
        if predicted and ground_truth:       tp += 1  # Correctly identified as AI
        elif predicted and not ground_truth: fp += 1  # False positive (said AI, but wasn't)
        elif not predicted and ground_truth: fn += 1  # False negative (missed AI article)
        else:                               tn += 1  # Correctly identified as non-AI
    
    if labeled_cases == 0:
        logger.warning("No labeled cases found in dataset")
        return {"error": "No ground truth labels found"}
    
    # Calculate metrics
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0  
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (tp + tn) / (tp + fp + tn + fn) if (tp + fp + tn + fn) > 0 else 0
    
    metrics = {
        "evaluation_metrics": {
            "precision": round(precision, 3),
            "recall": round(recall, 3), 
            "f1_score": round(f1_score, 3),
            "accuracy": round(accuracy, 3)
        },
        "confusion_matrix": {
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn, 
            "false_negatives": fn
        },
        "dataset_stats": {
            "total_cases": len(dataset["test_cases"]),
            "labeled_cases": labeled_cases,
            "unlabeled_cases": len(dataset["test_cases"]) - labeled_cases,
            "ground_truth_ai_relevant": tp + fn,
            "ground_truth_not_ai_relevant": fp + tn,
            "predicted_ai_relevant": tp + fp,
            "predicted_not_ai_relevant": tn + fn
        }
    }
    
    return metrics


def analyze_test_dataset(test_dataset_path: str):
    """
    Analyze the test dataset and provide statistics.
    
    Args:
        test_dataset_path: Path to the test dataset JSON file
    """
    with open(test_dataset_path, 'r') as f:
        dataset = json.load(f)
    
    total_cases = len(dataset["test_cases"])
    ai_relevant = sum(1 for tc in dataset["test_cases"] if tc["filtering_results"]["passed_ai_filter"])
    
    # Check how many are manually labeled
    labeled_cases = sum(1 for tc in dataset["test_cases"] if tc["ground_truth"]["is_ai_relevant"] is not None)
    
    # Source distribution
    sources = {}
    for tc in dataset["test_cases"]:
        source = tc["input"]["source_url"]
        sources[source] = sources.get(source, 0) + 1
    
    print(f"\n=== Test Dataset Analysis ===")
    print(f"Total articles: {total_cases}")
    print(f"Labeled articles: {labeled_cases} ({labeled_cases/total_cases*100:.1f}%)")
    print(f"AI-relevant (predicted): {ai_relevant} ({ai_relevant/total_cases*100:.1f}%)")
    print(f"Not AI-relevant (predicted): {total_cases - ai_relevant} ({(total_cases - ai_relevant)/total_cases*100:.1f}%)")
    print(f"\nSource distribution:")
    for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
        print(f"  {source}: {count} articles ({count/total_cases*100:.1f}%)")
    
    # If we have labeled data, calculate metrics
    if labeled_cases > 0:
        print(f"\n=== Evaluation Metrics ===")
        metrics = calculate_evaluation_metrics(test_dataset_path)
        if "error" not in metrics:
            eval_metrics = metrics["evaluation_metrics"]
            confusion = metrics["confusion_matrix"]
            
            print(f"Precision: {eval_metrics['precision']:.3f}")
            print(f"Recall: {eval_metrics['recall']:.3f}")
            print(f"F1-Score: {eval_metrics['f1_score']:.3f}")
            print(f"Accuracy: {eval_metrics['accuracy']:.3f}")
            print(f"\nConfusion Matrix:")
            print(f"  True Positives: {confusion['true_positives']}")
            print(f"  False Positives: {confusion['false_positives']}")
            print(f"  True Negatives: {confusion['true_negatives']}")
            print(f"  False Negatives: {confusion['false_negatives']}")
    
    return {
        "total_cases": total_cases,
        "labeled_cases": labeled_cases,
        "ai_relevant": ai_relevant,
        "not_ai_relevant": total_cases - ai_relevant,
        "sources": sources
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "verify" and len(sys.argv) == 3:
            # Verify Langfuse dataset format
            langfuse_path = sys.argv[2]
            print(f"Verifying Langfuse dataset: {langfuse_path}")
            verify_langfuse_dataset(langfuse_path)
            
        elif command == "convert" and len(sys.argv) == 3:
            # Convert test dataset to Langfuse format
            test_dataset_path = sys.argv[2]
            print(f"Converting to Langfuse format: {test_dataset_path}")
            langfuse_path = create_langfuse_evaluation_dataset(test_dataset_path)
            print(f"Langfuse dataset created: {langfuse_path}")
            verify_langfuse_dataset(langfuse_path)
            
        else:
            print("Usage:")
            print("  python test_dataset_generator.py verify <langfuse_dataset.json>")
            print("  python test_dataset_generator.py convert <test_dataset.json>")
    else:
        # Example usage
        print("Test dataset generator for AI content filtering")
        print("\nUsage:")
        print("  python test_dataset_generator.py verify <langfuse_dataset.json>")
        print("  python test_dataset_generator.py convert <test_dataset.json>")