"""YEN Cuisine Japonaise — knowledge base.

**These are the venue's REAL answers**, recovered from the knowledge base the
restaurant actually maintains (SadieAI tenant 37487, captured 25 Jul 2026). Do not
invent or "improve" them — a plausible-sounding wrong answer is worse than no
answer. If a caller asks something not covered here, the agent must take a message
rather than guess (see prompts.py).

French is Québécois register: **always "vous", never "tu"**; "ça" not "cela".
Bill 96 makes French service a statutory right in Quebec.

Known gap: the venue has never answered its **cancellation/refund policy**, and
that single blank drove multiple human transfers in their call data. It is the
top item in docs/YEN_owner_questions.xlsx.
"""

from __future__ import annotations

# -- Venue facts (single source of truth) ------------------------------------
VENUE_NAME = "YEN Cuisine Japonaise"
ADDRESS = "2157 Rue Mackay, Montréal, QC H3G 2J2"
PHONE = "514-543-3354"
TIMEZONE = "America/Toronto"  # their config says America/New_York; same offset

#: Parties above this are arranged by staff. **6 is a Libro API ceiling**, not a
#: policy: the availability endpoint only ever returns party sizes 1-6, so 7+
#: cannot be checked or booked programmatically at all. See libro_private.py.
MAX_ONLINE_PARTY = 6
#: How long a table is held — from the venue's own booking policy.
TURN_MINUTES_SMALL = 90   # parties under 6
TURN_MINUTES_LARGE = 120  # parties of 7+
LARGE_PARTY_THRESHOLD = 6

FAQ: dict[str, dict[str, str]] = {
    "hours": {
        "en": ("We're open for lunch Monday through Saturday, 11:30 to 2:30, and "
               "for dinner every night from 5 to 9:30."),
        "fr": ("Nous sommes ouverts pour le dîner du lundi au samedi, de 11 h 30 à "
               "14 h 30, et pour le souper tous les soirs de 17 h à 21 h 30."),
    },
    "location": {
        "en": f"We're at {ADDRESS} — on Mackay, in downtown Montreal.",
        "fr": "Nous sommes au 2157, rue Mackay, au centre-ville de Montréal.",
    },
    "directions": {
        "en": f"We're at {ADDRESS}. I can text you a map link if that helps.",
        "fr": "Nous sommes au 2157, rue Mackay. Je peux vous envoyer un lien vers la carte par texto.",
    },
    "parking": {
        "en": ("We're a five-minute walk from Guy-Concordia metro, on the Concordia "
               "campus. Parking is limited paid street parking from the city."),
        "fr": ("Nous sommes à cinq minutes de marche du métro Guy-Concordia, sur le "
               "campus de Concordia. Le stationnement est limité — du stationnement "
               "de rue payant de la ville."),
    },
    "accessibility": {
        "en": ("I should mention there are four or five steps going down — our unit "
               "is in the sub-basement of the building."),
        "fr": ("Je dois vous mentionner qu'il y a quatre ou cinq marches à descendre — "
               "notre local est au sous-sol du bâtiment."),
    },
    "dietary": {
        "en": ("We do have fish, soy and gluten in our kitchen. We have many "
               "vegetarian options; we can't always fully accommodate vegan, but "
               "we'll do what we can. Our chicken is halal. Just let the staff know "
               "about any allergies or restrictions and we'll do our best."),
        "fr": ("Nous avons du poisson, du soja et du gluten dans notre cuisine. Nous "
               "avons plusieurs options végétariennes; pour le végétalien nous ne "
               "pouvons pas toujours tout accommoder, mais nous ferons de notre "
               "mieux. Notre poulet est halal. Dites-le au personnel et nous ferons "
               "tout notre possible."),
    },
    "about": {
        "en": ("We're a chic Japanese bistro with a large and diverse menu — premium "
               "ingredients at accessible prices."),
        "fr": ("Nous sommes un bistro japonais chic avec un menu vaste et varié — des "
               "ingrédients de qualité à prix accessibles."),
    },
    "kids": {
        "en": "We don't have a kids menu, and we have one high chair available.",
        "fr": "Nous n'avons pas de menu pour enfants, et nous avons une chaise haute disponible.",
    },
    "payment": {
        "en": "We take cash, Visa, Mastercard and American Express.",
        "fr": "Nous acceptons l'argent comptant, Visa, Mastercard et American Express.",
    },
    "deposits": {
        "en": "We don't take deposits or prepayment for reservations.",
        "fr": "Nous ne prenons ni dépôt ni prépaiement pour les réservations.",
    },
    "service_fees": {
        "en": "We don't charge any service fees.",
        "fr": "Nous ne facturons aucuns frais de service.",
    },
    "takeout": {
        "en": ("Take-out and delivery are available through our website. I can text "
               "you the link if you'd like."),
        "fr": ("Les commandes pour emporter et la livraison sont disponibles sur notre "
               "site web. Je peux vous envoyer le lien par texto si vous voulez."),
    },
    "promo": {
        "en": ("We have fifteen percent off take-out plus free delivery with the code "
               "YEN15 — that's on our website only, on orders over fifty dollars."),
        "fr": ("Nous offrons quinze pour cent de rabais sur les commandes à emporter et "
               "la livraison gratuite avec le code YEN15 — sur notre site web seulement, "
               "pour les commandes de plus de cinquante dollars."),
    },
    "happy_hour": {
        "en": "We don't have a happy hour.",
        "fr": "Nous n'avons pas de « happy hour ».",
    },
    "menu": {
        "en": ("We serve Japanese cuisine. Our full menu is on our website — I can text "
               "you the link."),
        "fr": ("Nous servons une cuisine japonaise. Notre menu complet est sur notre site "
               "web — je peux vous envoyer le lien par texto."),
    },
    "seasonal_menu": {
        "en": "We don't have any seasonal menus running at the moment.",
        "fr": "Nous n'avons pas de menu saisonnier en ce moment.",
    },
    "booking_policy": {
        "en": ("We hold tables for an hour and a half for parties under six, and two "
               "hours for parties of seven or more."),
        "fr": ("Nous gardons les tables une heure et demie pour les groupes de moins de "
               "six personnes, et deux heures pour les groupes de sept et plus."),
    },
    "large_groups": {
        "en": ("For groups larger than seven, our team arranges the seating directly — "
               "I'll take your name and number and they'll call you back."),
        "fr": ("Pour les groupes de plus de sept personnes, notre équipe organise le "
               "placement directement — je prends votre nom et votre numéro et on vous "
               "rappelle."),
    },
    "outdoor_seating": {
        "en": "We don't have outdoor seating or a terrace.",
        "fr": "Nous n'avons pas de terrasse ni de places à l'extérieur.",
    },
    "pets": {
        "en": "I'm sorry, we don't allow pets.",
        "fr": "Je suis désolé, les animaux ne sont pas admis.",
    },
    "age_restrictions": {
        "en": "There are no age restrictions — everyone's welcome.",
        "fr": "Il n'y a aucune restriction d'âge — tout le monde est bienvenu.",
    },
    "byo": {
        "en": "We don't offer bring-your-own.",
        "fr": "Nous n'offrons pas l'option « apportez votre vin ».",
    },
    "entertainment": {
        "en": "We don't have live entertainment or events.",
        "fr": "Nous n'avons pas de spectacles ni d'événements.",
    },
    "reservations": {
        "en": ("I can book, change or cancel a table for you right now. For groups over "
               "seven I'll take a message so our team can arrange it."),
        "fr": ("Je peux réserver, modifier ou annuler une table pour vous tout de suite. "
               "Pour les groupes de plus de sept, je prendrai un message pour notre équipe."),
    },
    # The owner's answer, verbatim, was "No cancellation/No-show" — read as: there
    # is no penalty or fee, not that cancelling is forbidden. Worded here so it is
    # true under either reading, and flagged for confirmation.
    # TODO: confirm the intended meaning before launch.
    "cancellation_policy": {
        "en": ("There's no cancellation fee and no no-show charge — just let us know "
               "if your plans change so we can free the table."),
        "fr": ("Il n'y a pas de frais d'annulation ni de frais pour absence — "
               "faites-nous simplement signe si vos plans changent, pour que nous "
               "puissions libérer la table."),
    },
    # Prices are deliberately absent: the owner asked the agent NEVER to discuss
    # them and to redirect to the online menu instead. See prompts.py.
}

TOPICS = sorted(FAQ.keys())


def answer(topic: str, *, locale: str = "en") -> str | None:
    entry = FAQ.get(topic.strip().lower())
    if not entry:
        return None
    return entry.get(locale, entry.get("en"))
