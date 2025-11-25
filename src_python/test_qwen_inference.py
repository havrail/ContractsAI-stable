"""
Qwen VL Inference Test Harness

Bu script, Qwen3-VL-8B modeli ile prompt engineering testleri yapar.
Amaç: Vision ve text extraction doğruluğunu ölçmek, prompt iyileştirmeleri test etmek.

Kullanım:
    python src_python/test_qwen_inference.py --pdf <pdf_path> --ground_truth <json_path>
    python src_python/test_qwen_inference.py --batch <test_folder>
"""

import argparse
import json
import os
import time
from typing import Dict, List, Optional
from pathlib import Path

from pdf_quality_checker import PDFQualityChecker
from prompt_templates import build_contract_extraction_messages, parse_json_response
from model_provider import ModelProvider
from pdf2image import convert_from_path
from config import POPPLER_PATH
import base64
import io
from PIL import Image


def load_ground_truth(json_path: str) -> Dict:
    """Load ground truth JSON for comparison."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def convert_images_to_b64(images: List[Image.Image]) -> List[str]:
    """Convert PIL images to base64 strings."""
    b64_list = []
    for img in images:
        try:
            img_resized = img.copy()
            img_resized.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img_resized.save(buf, format="JPEG", quality=60)
            b64_list.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
        except Exception:
            pass
    return b64_list


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract raw text from PDF (simple method)."""
    from PyPDF2 import PdfReader
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"
        return text
    except Exception as e:
        print(f"Text extraction error: {e}")
        return ""


def calculate_field_accuracy(predicted: Dict, ground_truth: Dict) -> Dict[str, float]:
    """Calculate per-field accuracy."""
    fields = ["contract_name", "signing_party", "address", "country", "signed_date", "both_signed"]
    scores = {}
    
    for field in fields:
        pred_val = str(predicted.get(field, "")).strip().lower()
        gt_val = str(ground_truth.get(field, "")).strip().lower()
        
        if field == "both_signed":
            scores[field] = 1.0 if pred_val == gt_val else 0.0
        else:
            if pred_val == gt_val:
                scores[field] = 1.0
            elif pred_val in gt_val or gt_val in pred_val:
                scores[field] = 0.5  # Partial match
            else:
                scores[field] = 0.0
    
    overall = sum(scores.values()) / len(scores) if scores else 0.0
    scores["overall"] = overall
    return scores


def test_single_pdf(pdf_path: str, ground_truth_path: Optional[str] = None, use_vision: bool = True) -> Dict:
    """Test extraction on a single PDF."""
    print(f"\n{'='*60}")
    print(f"Testing: {os.path.basename(pdf_path)}")
    print(f"{'='*60}")
    
    # 1. Quality Analysis
    quality_checker = PDFQualityChecker()
    quality_report = None
    try:
        quality_report = quality_checker.analyze(pdf_path)
        print(f"Quality Score: {getattr(quality_report, 'score', 'N/A')}")
        print(f"Is Scanned: {getattr(quality_report, 'is_scanned', False)}")
    except Exception as e:
        print(f"Quality check failed: {e}")
    
    # 2. Extract text
    text = extract_text_from_pdf(pdf_path)
    print(f"Extracted Text Length: {len(text)} chars")
    
    # 3. Get images for vision model
    images_b64 = None
    if use_vision:
        try:
            images = convert_from_path(pdf_path, dpi=150, poppler_path=POPPLER_PATH)
            images_b64 = convert_images_to_b64(images[:4])  # Max 4 pages
            print(f"Vision Images: {len(images_b64)}")
        except Exception as e:
            print(f"Image extraction failed: {e}")
            images_b64 = None
    
    # 4. Build messages
    messages = build_contract_extraction_messages(
        text=text,
        filename=os.path.basename(pdf_path),
        images_b64=images_b64,
        quality_report=quality_report,
        adaptive_hint=None
    )
    
    # 5. Run inference
    provider = ModelProvider()
    start_time = time.time()
    try:
        raw_response = provider.chat(messages)
        inference_time = time.time() - start_time
        print(f"Inference Time: {inference_time:.2f}s")
        
        # Parse response
        extracted = parse_json_response(raw_response)
        print(f"\n--- Extracted Data ---")
        print(json.dumps(extracted, indent=2, ensure_ascii=False))
        
        # 6. Compare with ground truth if available
        if ground_truth_path and os.path.exists(ground_truth_path):
            ground_truth = load_ground_truth(ground_truth_path)
            accuracy = calculate_field_accuracy(extracted, ground_truth)
            print(f"\n--- Accuracy Scores ---")
            for field, score in accuracy.items():
                print(f"{field}: {score*100:.1f}%")
            
            return {
                "filename": os.path.basename(pdf_path),
                "extracted": extracted,
                "ground_truth": ground_truth,
                "accuracy": accuracy,
                "inference_time": inference_time,
                "quality_score": getattr(quality_report, 'score', None)
            }
        else:
            return {
                "filename": os.path.basename(pdf_path),
                "extracted": extracted,
                "inference_time": inference_time,
                "quality_score": getattr(quality_report, 'score', None)
            }
    
    except Exception as e:
        print(f"Inference failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "filename": os.path.basename(pdf_path),
            "error": str(e)
        }


def test_batch(test_folder: str, output_report: str = "test_results.json"):
    """Run batch tests on multiple PDFs with ground truth files."""
    test_folder_path = Path(test_folder)
    if not test_folder_path.exists():
        print(f"Test folder not found: {test_folder}")
        return
    
    # Find all PDFs and their corresponding ground truth JSONs
    pdf_files = list(test_folder_path.glob("*.pdf"))
    results = []
    
    for pdf_path in pdf_files:
        gt_path = pdf_path.with_suffix(".json")
        result = test_single_pdf(str(pdf_path), str(gt_path) if gt_path.exists() else None)
        results.append(result)
    
    # Calculate overall statistics
    accuracies = [r["accuracy"]["overall"] for r in results if "accuracy" in r]
    if accuracies:
        avg_accuracy = sum(accuracies) / len(accuracies)
        print(f"\n{'='*60}")
        print(f"BATCH TEST RESULTS")
        print(f"{'='*60}")
        print(f"Total PDFs: {len(pdf_files)}")
        print(f"Average Accuracy: {avg_accuracy*100:.1f}%")
        print(f"Min Accuracy: {min(accuracies)*100:.1f}%")
        print(f"Max Accuracy: {max(accuracies)*100:.1f}%")
    
    # Save results
    with open(output_report, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\nDetailed results saved to: {output_report}")


def main():
    parser = argparse.ArgumentParser(description="Qwen VL Inference Test Harness")
    parser.add_argument("--pdf", help="Single PDF file to test")
    parser.add_argument("--ground_truth", help="Ground truth JSON file for single PDF")
    parser.add_argument("--batch", help="Batch test folder with PDFs and corresponding JSONs")
    parser.add_argument("--output", default="test_results.json", help="Output report file for batch mode")
    parser.add_argument("--no-vision", action="store_true", help="Disable vision model (text only)")
    
    args = parser.parse_args()
    
    if args.pdf:
        # Single PDF test
        test_single_pdf(args.pdf, args.ground_truth, use_vision=not args.no_vision)
    elif args.batch:
        # Batch test
        test_batch(args.batch, args.output)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
