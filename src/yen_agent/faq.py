"""Yen Restaurant FAQ knowledge base.

NOTE: These are placeholder facts for the POC demo. Replace with the
restaurant's real hours, address, and policies before any live use. The agent
should only state facts present here; anything outside this base should be
deferred to a human / message.
"""

from __future__ import annotations

# Bilingual answers keyed by topic. The agent picks the locale of the caller.
FAQ: dict[str, dict[str, str]] = {
    "hours": {
        "en": (
            "We're open for lunch Tuesday to Friday from 11:30 AM to 2 PM, and "
            "for dinner Tuesday to Sunday from 5 PM to 10 PM. We're closed on "
            "Mondays."
        ),
        "fr": (
            "Nous sommes ouverts pour le dîner du mardi au vendredi de 11 h 30 à "
            "14 h, et pour le souper du mardi au dimanche de 17 h à 22 h. Nous "
            "sommes fermés le lundi."
        ),
    },
    "location": {
        "en": "We're located in downtown Montreal. I can text you the exact address if you like.",
        "fr": "Nous sommes situés au centre-ville de Montréal. Je peux vous envoyer l'adresse exacte par texto si vous voulez.",
    },
    "parking": {
        "en": "There's paid street parking nearby and a public parking garage about a block away.",
        "fr": "Il y a du stationnement payant dans la rue tout près et un stationnement public à environ un coin de rue.",
    },
    "menu": {
        "en": "We serve contemporary Asian cuisine, with a dinner tasting menu and à la carte options. We can accommodate most dietary needs with notice.",
        "fr": "Nous servons une cuisine asiatique contemporaine, avec un menu dégustation le soir et des options à la carte. Nous pouvons répondre à la plupart des besoins alimentaires sur préavis.",
    },
    "dietary": {
        "en": "We can accommodate vegetarian, vegan, and most allergy needs if you let us know in advance — just add a note to your reservation.",
        "fr": "Nous pouvons accommoder les régimes végétariens, végétaliens et la plupart des allergies si vous nous prévenez à l'avance — ajoutez simplement une note à votre réservation.",
    },
    "reservations": {
        "en": "I can book, change, or cancel a reservation for you right now over the phone. For groups larger than our online limit, I'll take a message for the team.",
        "fr": "Je peux réserver, modifier ou annuler une réservation pour vous tout de suite au téléphone. Pour les groupes plus grands que notre limite en ligne, je prendrai un message pour l'équipe.",
    },
    "payment": {
        "en": "Most reservations don't require a deposit. Our tasting menu may require a card to hold the table; if so, you'll get a secure payment link by text.",
        "fr": "La plupart des réservations ne nécessitent pas de dépôt. Notre menu dégustation peut exiger une carte pour garantir la table ; le cas échéant, vous recevrez un lien de paiement sécurisé par texto.",
    },
}

TOPICS = sorted(FAQ.keys())


def answer(topic: str, *, locale: str = "en") -> str | None:
    """Return the FAQ answer for ``topic`` in ``locale`` (falls back to en)."""
    entry = FAQ.get(topic.strip().lower())
    if not entry:
        return None
    return entry.get(locale, entry.get("en"))
