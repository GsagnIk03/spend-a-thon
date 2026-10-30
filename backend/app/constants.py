CATEGORIES = [
    {"id": "food", "label": "Food & Dining", "emoji": "🍽️", "color": "#f97316"},
    {"id": "groceries", "label": "Groceries", "emoji": "🛒", "color": "#22c55e"},
    {"id": "transport", "label": "Transport", "emoji": "🚕", "color": "#eab308"},
    {"id": "fuel", "label": "Fuel", "emoji": "⛽", "color": "#b45309"},
    {"id": "shopping", "label": "Shopping", "emoji": "🛍️", "color": "#ec4899"},
    {"id": "bills", "label": "Bills & Utilities", "emoji": "💡", "color": "#06b6d4"},
    {"id": "rent", "label": "Rent", "emoji": "🏠", "color": "#6366f1"},
    {"id": "health", "label": "Health & Medical", "emoji": "💊", "color": "#ef4444"},
    {"id": "entertainment", "label": "Entertainment", "emoji": "🎬", "color": "#8b5cf6"},
    {"id": "travel", "label": "Travel", "emoji": "✈️", "color": "#0ea5e9"},
    {"id": "education", "label": "Education", "emoji": "📚", "color": "#14b8a6"},
    {"id": "emi", "label": "EMI & Loans", "emoji": "🏦", "color": "#64748b"},
    {"id": "subscriptions", "label": "Subscriptions", "emoji": "🔁", "color": "#d946ef"},
    {"id": "personal", "label": "Personal Care", "emoji": "💇", "color": "#f43f5e"},
    {"id": "gifts", "label": "Gifts & Donations", "emoji": "🎁", "color": "#84cc16"},
    {"id": "other", "label": "Other", "emoji": "📦", "color": "#94a3b8"},
]
CATEGORY_IDS = {c["id"] for c in CATEGORIES}
CATEGORY_LABELS = {c["id"]: c["label"] for c in CATEGORIES}

CREDIT_CARD = "Credit card"
PAYMENT_METHODS = [
    "Cash", "Google Pay", "PhonePe", "Paytm", "Other UPI",
    CREDIT_CARD, "Debit card", "Net banking", "Wallet", "Other",
]

CATEGORY_COLORS = [
    "#f97316", "#22c55e", "#eab308", "#ec4899", "#06b6d4", "#6366f1", "#ef4444",
    "#8b5cf6", "#0ea5e9", "#14b8a6", "#64748b", "#d946ef", "#84cc16", "#a16207",
]
CARD_COLORS = ["#0f766e", "#1e3a8a", "#7c2d12", "#581c87", "#111827", "#9f1239", "#155e75", "#3f6212"]

MAX_RANGE_MONTHS = 24
