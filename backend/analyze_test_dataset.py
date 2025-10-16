#!/usr/bin/env python3
"""
Simple test dataset analyzer that can be run standalone.
Analyzes existing test datasets and calculates evaluation metrics.

Usage:
    python analyze_test_dataset.py path/to/your/test_dataset.json
"""

import json
import sys
from pathlib import Path


def calculate_evaluation_metrics(test_data):
    """Calculate precision, recall, F1-score from test dataset."""
    tp = fp = tn = fn = 0
    labeled_cases = 0
    
    for case in test_data["test_cases"]:
        ground_truth = case["ground_truth"]["is_ai_relevant"]
        if ground_truth is None:
            continue  # Skip unlabeled cases
            
        labeled_cases += 1
        predicted = case["filtering_results"]["passed_ai_filter"]
        
        if predicted and ground_truth:       tp += 1
        elif predicted and not ground_truth: fp += 1
        elif not predicted and ground_truth: fn += 1
        else:                               tn += 1
    
    if labeled_cases == 0:
        return {"error": "No ground truth labels found"}
    
    # Calculate metrics
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0  
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (tp + tn) / (tp + fp + tn + fn) if (tp + fp + tn + fn) > 0 else 0
    
    return {
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
            "total_cases": len(test_data["test_cases"]),
            "labeled_cases": labeled_cases,
            "unlabeled_cases": len(test_data["test_cases"]) - labeled_cases,
            "ground_truth_ai_relevant": tp + fn,
            "ground_truth_not_ai_relevant": fp + tn,
            "predicted_ai_relevant": tp + fp,
            "predicted_not_ai_relevant": tn + fn
        }
    }


def analyze_dataset(filepath):
    """Analyze test dataset and print statistics."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            dataset = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found.")
        return
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{filepath}': {e}")
        return
    
    total_cases = len(dataset["test_cases"])
    ai_relevant = sum(1 for tc in dataset["test_cases"] if tc["filtering_results"]["passed_ai_filter"])
    labeled_cases = sum(1 for tc in dataset["test_cases"] if tc["ground_truth"]["is_ai_relevant"] is not None)
    
    # Source distribution
    sources = {}
    for tc in dataset["test_cases"]:
        source = tc["input"]["source_url"]
        sources[source] = sources.get(source, 0) + 1
    
    print(f"\n=== Test Dataset Analysis: {Path(filepath).name} ===")
    print(f"Total articles: {total_cases}")
    print(f"Labeled articles: {labeled_cases} ({labeled_cases/total_cases*100:.1f}%)")
    print(f"AI-relevant (predicted): {ai_relevant} ({ai_relevant/total_cases*100:.1f}%)")
    print(f"Not AI-relevant (predicted): {total_cases - ai_relevant} ({(total_cases - ai_relevant)/total_cases*100:.1f}%)")
    
    print(f"\nSource distribution:")
    for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
        source_short = source if len(source) <= 50 else source[:47] + "..."
        print(f"  {source_short}: {count} articles ({count/total_cases*100:.1f}%)")
    
    # Calculate evaluation metrics if we have labeled data
    if labeled_cases > 0:
        print(f"\n=== Evaluation Metrics ===")
        metrics = calculate_evaluation_metrics(dataset)
        if "error" not in metrics:
            eval_metrics = metrics["evaluation_metrics"]
            confusion = metrics["confusion_matrix"]
            stats = metrics["dataset_stats"]
            
            print(f"Precision: {eval_metrics['precision']:.3f} ({confusion['true_positives']}/{confusion['true_positives'] + confusion['false_positives']}) - Of predicted AI articles, how many were correct?")
            print(f"Recall: {eval_metrics['recall']:.3f} ({confusion['true_positives']}/{confusion['true_positives'] + confusion['false_negatives']}) - Of actual AI articles, how many were found?")
            print(f"F1-Score: {eval_metrics['f1_score']:.3f} - Balanced measure of precision and recall")
            print(f"Accuracy: {eval_metrics['accuracy']:.3f} - Overall correctness")
            
            print(f"\nConfusion Matrix:")
            print(f"                    Predicted")
            print(f"                 AI    Not-AI")
            print(f"Actual    AI    {confusion['true_positives']:3d}     {confusion['false_negatives']:3d}")
            print(f"       Not-AI    {confusion['false_positives']:3d}     {confusion['true_negatives']:3d}")
            
            print(f"\nInterpretation:")
            if eval_metrics['precision'] < 0.7:
                print("Low precision - many false positives (non-AI articles classified as AI)")
            if eval_metrics['recall'] < 0.7:
                print("Low recall - missing many AI articles (false negatives)")
            if eval_metrics['f1_score'] > 0.8:
                print("Good overall performance (F1 > 0.8)")
            elif eval_metrics['f1_score'] > 0.6:
                print("Moderate performance (F1 > 0.6)")
            else:
                print("Poor performance (F1 ≤ 0.6) - needs improvement")
                
        else:
            print("Cannot calculate metrics: No ground truth labels found")
    else:
        print(f"\nTo get evaluation metrics, manually label some articles by setting:")
        print(f"   'is_ai_relevant': true/false in the 'ground_truth' section")


def main():
    if len(sys.argv) != 2:
        print("Usage: python analyze_test_dataset.py <path_to_test_dataset.json>")
        print("\nExample:")
        print("  python analyze_test_dataset.py ../test_datasets/ai_filter_test_dataset_20251015_152252.json")
        sys.exit(1)
    
    filepath = sys.argv[1]
    analyze_dataset(filepath)


if __name__ == "__main__":
    main()