"""YEN Cuisine Japonaise — FAQ knowledge base.

Facts below are drawn from public listings (the restaurant's site, OpenTable,
Yelp, Tourisme Montréal) as of mid-2026:

  YEN Cuisine Japonaise — 2157 Rue Mackay, Montréal, QC H3G 2J2  (downtown / Ville-Marie)
  (514) 543-3354 — refined Japanese cuisine, open since 2018, intimate room
  Lunch: Mon-Sat ~11:30-14:30   Dinner: daily ~17:00-21:30

Hours and policies on third-party sites occasionally disagree, so **confirm the
exact current hours and any deposit/large-group policy with the restaurant
before go-live.** The agent must only state facts present here; anything else is
deferred to a human / message. The "up to 8 guests" figure mirrors the online
booking cap enforced by the floor-plan engine (mock_libro/floorplan.py).
"""

from __future__ import annotations

FAQ: dict[str, dict[str, str]] = {
    "hours": {
        "en": (
            "We serve lunch Monday through Saturday from 11:30 in the morning to "
            "2:30 in the afternoon, and dinner every evening from 5 to 9:30."
        ),
        "fr": (
            "Nous servons le dîner du lundi au samedi de 11 h 30 à 14 h 30, et le "
            "souper tous les soirs de 17 h à 21 h 30."
        ),
    },
    "location": {
        "en": (
            "We're at 2157 Mackay Street in downtown Montreal, near Concordia. "
            "I can text you the address if that helps."
        ),
        "fr": (
            "Nous sommes au 2157, rue Mackay, au centre-ville de Montréal, près de "
            "Concordia. Je peux vous envoyer l'adresse par texto si vous voulez."
        ),
    },
    "parking": {
        "en": "There's paid street parking on Mackay and nearby, plus public garages a short walk away.",
        "fr": "Il y a du stationnement payant sur Mackay et à proximité, ainsi que des stationnements publics à quelques pas.",
    },
    "menu": {
        "en": (
            "We serve refined, authentic Japanese cuisine with a modern touch — "
            "seasonal dishes, sushi, and small plates. We can accommodate most "
            "dietary needs with a little notice."
        ),
        "fr": (
            "Nous offrons une cuisine japonaise authentique et raffinée avec une "
            "touche moderne — des plats de saison, des sushis et des petites "
            "assiettes. Nous pouvons accommoder la plupart des régimes sur préavis."
        ),
    },
    "dietary": {
        "en": "Let us know about vegetarian, vegan, or allergy needs in advance and we'll do our best — just add a note to the reservation.",
        "fr": "Indiquez-nous à l'avance vos besoins végétariens, végétaliens ou allergies et nous ferons de notre mieux — ajoutez simplement une note à la réservation.",
    },
    "reservations": {
        "en": (
            "I can book, change, or cancel a table for you right now. We seat "
            "parties of up to 8 online — for anything larger I'll take a message "
            "so our team can arrange it."
        ),
        "fr": (
            "Je peux réserver, modifier ou annuler une table pour vous tout de "
            "suite. Nous plaçons en ligne les groupes jusqu'à 8 personnes — pour "
            "plus grand, je prendrai un message pour que notre équipe l'organise."
        ),
    },
    "large_groups": {
        "en": "For groups larger than 8, our team arranges the seating directly — I'll take your name and number and they'll call you back.",
        "fr": "Pour les groupes de plus de 8 personnes, notre équipe organise le placement directement — je prends votre nom et numéro et on vous rappelle.",
    },
    "payment": {
        "en": "Most reservations don't require a deposit. If a particular booking needs a card to hold the table, you'll get a secure payment link by text.",
        "fr": "La plupart des réservations ne nécessitent pas de dépôt. Si une réservation exige une carte pour garantir la table, vous recevrez un lien de paiement sécurisé par texto.",
    },
}

TOPICS = sorted(FAQ.keys())


def answer(topic: str, *, locale: str = "en") -> str | None:
    entry = FAQ.get(topic.strip().lower())
    if not entry:
        return None
    return entry.get(locale, entry.get("en"))
