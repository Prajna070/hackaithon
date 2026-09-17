from typing import Dict, Any

from .ocr.text_extractor import TextExtractor
from .nlp.summarizer import summarize_text
from .nlp.skill_extractor import extract_skills
from .goal_predictor.goal_predictor import GoalPredictor


# Lazy singletons for heavy components
_text_extractor = None
_goal_predictor = None


def analyze_certificate(file_path: str) -> Dict[str, Any]:
    """
    Runs OCR → summarization → skill extraction → goal prediction
    Returns:
        {
            "summary": "...",
            "skills": [...],
            "goal": "..."
        }
    """
    # Step 1: OCR
    global _text_extractor
    if _text_extractor is None:
        _text_extractor = TextExtractor()
    text = _text_extractor.process(file_path)

    # Step 2: Summarize certificate
    summary = summarize_text(text)

    # Step 3: Extract skills
    skills = extract_skills(text)

    # Step 4: Predict career goal (top prediction)
    global _goal_predictor
    if _goal_predictor is None:
        _goal_predictor = GoalPredictor()
    predictions = _goal_predictor.predict_goals(skills, certificate_text=text, top_k=1)
    goal = predictions[0]["goal"] if predictions else "Unknown"

    return {
        "summary": summary,
        "skills": skills,
        "goal": goal,
    }
