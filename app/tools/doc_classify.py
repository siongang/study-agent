"""Document classification using LLM (Phase 3)."""
import json
import os
from typing import Optional

from google import genai
from google.genai import types


def classify_document(
    first_page: str,
    filename: str,
    full_text_sample: str = ""
) -> dict:
    """
    Classify document type using Gemini Flash LLM.
    
    Args:
        first_page: Text from first page of document
        filename: Original filename (can provide hints)
        full_text_sample: Optional sample of full text (first ~2000 chars)
    
    Returns:
        dict with:
            - doc_type: str (syllabus, exam_overview, textbook, other)
            - confidence: float (0.0-1.0)
            - reasoning: str (explanation from LLM)
    """
    # Configure Gemini (requires GOOGLE_API_KEY env var)
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        # Fallback to heuristic classification if no API key
        return _fallback_classify(first_page, filename)
    
    client = genai.Client(api_key=api_key)
    
    # Prepare context for classification
    context = f"""Filename: {filename}

First page:
{first_page[:2000]}
"""
    
    if full_text_sample:
        context += f"\n\nAdditional sample:\n{full_text_sample[:1000]}"
    
    # Prompt for classification
    prompt = f"""You are a document classifier for educational materials.

Classify this document into ONE of these categories:
1. **syllabus** - Course syllabus with grading, schedule, policies
2. **exam_overview** - Exam preparation document listing topics/chapters covered
3. **textbook** - Educational textbook with chapters and sections
4. **other** - Anything else (notes, assignments, etc.)

Analyze the document carefully and provide:
1. The most appropriate category
2. Confidence score (0.0 to 1.0)
3. Brief reasoning for your classification

{context}

Respond in JSON format:
{{
  "doc_type": "syllabus|exam_overview|textbook|other",
  "confidence": 0.95,
  "reasoning": "Brief explanation..."
}}"""
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",  # Latest, fastest, cheapest model
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,  # Low temperature for consistent classification
                response_mime_type="application/json"
            )
        )
        result = json.loads(response.text)
        
        # Validate response
        valid_types = {"syllabus", "exam_overview", "textbook", "other"}
        if result.get("doc_type") not in valid_types:
            result["doc_type"] = "other"
        
        if not 0.0 <= result.get("confidence", 0) <= 1.0:
            result["confidence"] = 0.5
        
        return result
        
    except Exception as e:
        # Fallback on error
        return {
            "doc_type": "other",
            "confidence": 0.3,
            "reasoning": f"Classification failed: {str(e)}"
        }


def _fallback_classify(first_page: str, filename: str) -> dict:
    """Fallback heuristic classification when LLM unavailable."""
    first_page_lower = first_page.lower()
    filename_lower = filename.lower()
    
    # Syllabus signals
    syllabus_signals = ["syllabus", "course outline", "grading", "final grade", "office hours"]
    if any(sig in filename_lower or sig in first_page_lower for sig in syllabus_signals):
        return {
            "doc_type": "syllabus",
            "confidence": 0.7,
            "reasoning": "Heuristic match: syllabus keywords found"
        }
    
    # Exam overview signals
    exam_signals = ["midterm", "final examination", "exam", "coverage:", "this examination covers"]
    if any(sig in filename_lower or sig in first_page_lower for sig in exam_signals):
        return {
            "doc_type": "exam_overview",
            "confidence": 0.7,
            "reasoning": "Heuristic match: exam keywords found"
        }
    
    # Textbook signals
    textbook_signals = ["chapter", "edition", "isbn"]
    if any(sig in filename_lower or sig in first_page_lower for sig in textbook_signals):
        return {
            "doc_type": "textbook",
            "confidence": 0.6,
            "reasoning": "Heuristic match: textbook keywords found"
        }
    
    return {
        "doc_type": "other",
        "confidence": 0.4,
        "reasoning": "Heuristic: no strong signals found"
    }
