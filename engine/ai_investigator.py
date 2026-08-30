"""
Phase 4: AI Anomaly Investigation using Google Gemini.

For anomalies that can't be resolved deterministically, sends context to
Gemini and gets a structured explanation + classification.
"""
import os
import json
from typing import Optional


def _get_gemini_client():
    """Initialize Gemini client."""
    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key or api_key == "your_gemini_api_key_here":
            return None
        client = genai.Client(api_key=api_key)
        return client
    except ImportError:
        return None


SYSTEM_PROMPT = """You are a financial reconciliation expert at Razorpay, India's leading payment gateway.

You are analyzing discrepancies between three financial ledgers:
1. Merchant's order records
2. Razorpay's payment transaction records  
3. Bank settlement deposit records

For each anomaly, analyze the provided context and respond with a JSON object containing:
{
    "root_cause": "One of: TIMING_MISMATCH, PARTIAL_REFUND, SPLIT_SETTLEMENT, DUPLICATE_PAYMENT, MISSING_RECORD, REQUIRES_MANUAL_REVIEW",
    "confidence": "One of: high, medium, low",
    "explanation": "A clear, human-readable explanation of what happened and why the discrepancy exists. Be specific — reference dates, amounts, and IDs.",
    "suggested_resolution": "What action should be taken to resolve this",
    "needs_manual_review": true/false
}

IMPORTANT:
- Be precise about amounts (use Rs. prefix)
- Reference specific dates and IDs from the context
- If you're unsure, set confidence to "low" and needs_manual_review to true
- Common causes: midnight cutoff timing, partial refunds, split settlements across days, network delays
- Respond ONLY with the JSON object, no extra text
"""


def investigate_anomaly(anomaly: dict, nearby_transactions: Optional[list] = None) -> dict:
    """
    Send an anomaly to Gemini for investigation.

    Args:
        anomaly: The anomaly dict from Phase 1/2/3
        nearby_transactions: Optional list of nearby transactions for context

    Returns:
        Dict with AI investigation results
    """
    client = _get_gemini_client()

    if client is None:
        # Fallback: return a basic classification without AI
        return _fallback_classification(anomaly)

    # Build context message
    context = f"ANOMALY TYPE: {anomaly.get('anomaly_type', 'UNKNOWN')}\n"
    context += f"ORDER/REF: {anomaly.get('order_id', 'N/A')}\n\n"

    if anomaly.get("merchant_data"):
        context += f"MERCHANT DATA:\n{json.dumps(anomaly['merchant_data'], indent=2, default=str)}\n\n"

    if anomaly.get("razorpay_data"):
        context += f"RAZORPAY DATA:\n{json.dumps(anomaly['razorpay_data'], indent=2, default=str)}\n\n"

    if anomaly.get("bank_data"):
        context += f"BANK DATA:\n{json.dumps(anomaly['bank_data'], indent=2, default=str)}\n\n"

    if anomaly.get("note"):
        context += f"DETECTION NOTE: {anomaly['note']}\n\n"

    if nearby_transactions:
        context += f"NEARBY TRANSACTIONS (for context):\n{json.dumps(nearby_transactions[:5], indent=2, default=str)}\n\n"

    context += "Analyze this discrepancy and provide your assessment as a JSON object."

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=context,
            config={
                "system_instruction": SYSTEM_PROMPT,
                "temperature": 0.1,  # Low temperature for consistent analysis
            },
        )

        # Parse the response
        response_text = response.text.strip()
        # Clean up markdown code blocks if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        result = json.loads(response_text)

        return {
            "ai_explanation": result.get("explanation", "No explanation provided."),
            "ai_classification": result.get("root_cause", "REQUIRES_MANUAL_REVIEW"),
            "ai_confidence": result.get("confidence", "low"),
            "ai_suggested_resolution": result.get("suggested_resolution", "Manual review recommended."),
            "needs_manual_review": result.get("needs_manual_review", True),
        }

    except json.JSONDecodeError:
        # If Gemini doesn't return valid JSON, extract what we can
        return {
            "ai_explanation": response_text if 'response_text' in dir() else "AI response parsing failed.",
            "ai_classification": "REQUIRES_MANUAL_REVIEW",
            "ai_confidence": "low",
            "ai_suggested_resolution": "Manual review recommended — AI response was not structured.",
            "needs_manual_review": True,
        }
    except Exception as e:
        return {
            "ai_explanation": f"AI investigation failed: {str(e)}",
            "ai_classification": "REQUIRES_MANUAL_REVIEW",
            "ai_confidence": "low",
            "ai_suggested_resolution": "Manual review required — AI service unavailable.",
            "needs_manual_review": True,
        }


def investigate_batch(anomalies: list, nearby_transactions_map: Optional[dict] = None) -> list:
    """
    Investigate a batch of anomalies with rate limiting.

    Args:
        anomalies: List of anomaly dicts
        nearby_transactions_map: Optional dict mapping order_id to nearby transactions

    Returns:
        List of anomaly dicts enriched with AI investigation results
    """
    import time

    results = []
    ai_call_count = 0

    for anomaly in anomalies:
        nearby = None
        if nearby_transactions_map:
            nearby = nearby_transactions_map.get(anomaly.get("order_id"))

        # Skip anomalies that are already deterministically resolved
        if anomaly.get("anomaly_type") in ("FEE_DISCREPANCY",):
            # Fee discrepancy is handled deterministically — no AI needed
            enriched = {**anomaly}
            enriched["ai_explanation"] = anomaly.get("note", "Detected by deterministic fee-rate check.")
            enriched["ai_classification"] = "FEE_DISCREPANCY"
            enriched["ai_confidence"] = "high"
            enriched["ai_suggested_resolution"] = "Verify fee rate with Razorpay account settings."
            enriched["needs_manual_review"] = False
            results.append(enriched)
            continue

        # Rate limiting: free tier = 5 requests/min, so wait 13s between calls
        if ai_call_count > 0:
            time.sleep(13)

        # Retry with backoff on rate limit errors
        max_retries = 3
        for attempt in range(max_retries):
            ai_result = investigate_anomaly(anomaly, nearby)

            # Check if it was a rate limit error
            explanation = ai_result.get("ai_explanation", "")
            if "429" in explanation or "RESOURCE_EXHAUSTED" in explanation:
                wait_time = 15 * (attempt + 1)  # 15s, 30s, 45s
                time.sleep(wait_time)
                continue
            else:
                break

        enriched = {**anomaly, **ai_result}
        results.append(enriched)
        ai_call_count += 1

    return results


def _fallback_classification(anomaly: dict) -> dict:
    """
    Fallback classification when Gemini API is not available.
    Uses rule-based heuristics.
    """
    anomaly_type = anomaly.get("anomaly_type", "")

    explanations = {
        "MISSING_IN_RAZORPAY": {
            "ai_explanation": "This order exists in merchant records but has no corresponding Razorpay payment. The payment may have failed silently or was never initiated.",
            "ai_classification": "MISSING_RECORD",
            "ai_confidence": "medium",
            "ai_suggested_resolution": "Check with merchant if order was placed through a different payment channel.",
            "needs_manual_review": True,
        },
        "DUPLICATE_PAYMENT": {
            "ai_explanation": "Multiple Razorpay transactions found for the same order ID. Customer may have been charged twice due to a retry or system error.",
            "ai_classification": "DUPLICATE_PAYMENT",
            "ai_confidence": "high",
            "ai_suggested_resolution": "Initiate refund for the duplicate payment. Verify with customer.",
            "needs_manual_review": True,
        },
        "AMOUNT_MISMATCH": {
            "ai_explanation": "The merchant's recorded amount doesn't match the Razorpay transaction amount.",
            "ai_classification": "REQUIRES_MANUAL_REVIEW",
            "ai_confidence": "low",
            "ai_suggested_resolution": "Compare original order details with payment gateway records.",
            "needs_manual_review": True,
        },
        "SETTLEMENT_MISMATCH": {
            "ai_explanation": "A Razorpay settlement batch has no matching bank deposit. The settlement may have been split across multiple deposits or delayed.",
            "ai_classification": "SPLIT_SETTLEMENT",
            "ai_confidence": "medium",
            "ai_suggested_resolution": "Check if bank deposits on adjacent dates sum to the settlement total.",
            "needs_manual_review": True,
        },
        "ORPHAN_DEPOSIT": {
            "ai_explanation": "A bank deposit was found that doesn't match any Razorpay settlement. This could be from a different payment processor or a manual transfer.",
            "ai_classification": "MISSING_RECORD",
            "ai_confidence": "low",
            "ai_suggested_resolution": "Verify the deposit source with the bank narration and merchant's records.",
            "needs_manual_review": True,
        },
        "PARTIAL_REFUND": {
            "ai_explanation": "The net amount received is lower than expected. A partial refund may have been processed.",
            "ai_classification": "PARTIAL_REFUND",
            "ai_confidence": "medium",
            "ai_suggested_resolution": "Check Razorpay refund records for this order.",
            "needs_manual_review": False,
        },
    }

    return explanations.get(anomaly_type, {
        "ai_explanation": f"Anomaly of type '{anomaly_type}' detected. Requires investigation.",
        "ai_classification": "REQUIRES_MANUAL_REVIEW",
        "ai_confidence": "low",
        "ai_suggested_resolution": "Manual review required.",
        "needs_manual_review": True,
    })
