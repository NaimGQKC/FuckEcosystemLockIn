# YEN Cuisine Japonaise — voice reservation agent: owner questionnaire

The AI phone assistant is built and works today against realistic **placeholder**
data. To make it match YEN exactly (and to avoid it ever telling a caller
something wrong), we need the owner/manager to confirm the items below.

**How to use this:** answer inline after each `→`. Anything you leave blank keeps
the current placeholder default shown in *(italics)*. None of this is urgent for
a demo, but everything under **1–4** should be correct before real customers call.

The developer will translate these answers into config — you do **not** need any
technical detail. Where you see a placeholder, just tell us the real value.

---

## 1. Hours of operation  🕐  (most important)

Third-party sites disagree slightly, so please confirm the real current hours.

| Day | Lunch service | Dinner service |
|-----|---------------|----------------|
| Monday | *(11:30am–2:30pm)* → | *(5:00pm–9:30pm)* → |
| Tuesday | → | → |
| Wednesday | → | → |
| Thursday | → | → |
| Friday | → | → |
| Saturday | → | → |
| Sunday | *(closed for lunch)* → | *(5:00pm–9:30pm)* → |

- What is the **last reservation time** you accept for lunch and for dinner?
  *(currently 1:30pm lunch, 8:30pm dinner)* →
- Any regular closures or holidays the agent should know about (e.g. closed
  Sundays, statutory holidays, vacation weeks)? →
- Do lunch and dinner have different rules (menu, pricing, deposit)? →

## 2. Tables & seating  🪑  (this is how the agent avoids double-booking)

The agent knows your actual floor plan so it can seat the right table and
**combine tables** for bigger parties. Please describe your real tables.

- List each table and how many it seats. *(placeholder: three 2-seat tables,
  two 4-seat tables, one 4+one 2 in back, one 6-seat by the window, plus a
  4-seat sushi counter)* →
- Which tables can be **pushed together** for a larger group, and up to how many
  people? *(placeholder: two 4-tops combine to 8; three 2-tops are a zone)* →
- Is there **counter / bar seating**? How many seats, and is it walk-in only or
  reservable? →
- What is the **largest party you'll take as a normal online/phone reservation**?
  *(placeholder: 8 — anything larger the agent offers to take a message for)* →
- For parties above that limit (big groups, private events), what should the
  agent do? *(placeholder: take name + number + details for the team to call
  back)* → 
- Roughly **how long do you hold a table** (turn time) for a typical party?
  *(placeholder: 75 min lunch, 105 min dinner)* →

## 3. Reservation policy  📋

- Do you require a **deposit or credit card** to hold any reservation (e.g. large
  parties, tasting menu, weekends)? If so, when and how much? *(placeholder:
  none)* →
- **Cancellation / no-show policy** the agent should state if asked? →
- How far in advance can people book? *(placeholder: up to ~6 months)* →
- Can guests **modify or cancel** by phone through the agent, or must some
  changes go through staff? *(placeholder: agent can cancel/reschedule; some
  bookings may be marked staff-only)* →
- Do you keep a **waitlist** when full, and should the agent offer to add people
  to it? *(placeholder: not yet — agent offers another time/day)* →
- Should the agent handle **walk-ins / same-day** requests differently? →

## 4. What the agent tells callers  💬

- **Address** to confirm/read out: *(2157 Rue Mackay, Montréal, QC H3G 2J2)* →
- **Phone** for the reservation record / callbacks: *(514-543-3354)* →
- One or two sentences describing the **cuisine / experience** you want the agent
  to use: *(refined, authentic Japanese with a modern touch — seasonal dishes,
  sushi, small plates)* →
- **Parking / transit** guidance to give callers? *(placeholder: paid street
  parking + nearby garages)* →
- **Dietary / allergy** handling — what can you accommodate with notice?
  *(placeholder: vegetarian, vegan, most allergies with notice)* →
- Anything the agent should **never** promise or discuss? (pricing specifics,
  special events, media requests, etc.) →

## 5. Language  🌐

- Should the agent answer in **both French and English**, detecting the caller's
  language? *(placeholder: English first; French is one setting away)* →
- If bilingual, any preference on which language it **greets** in? →

## 6. Where messages & bookings go  📨

- When the agent **takes a message** (large party, special request, complaint),
  where should it go? (email address, SMS to a number, a shared inbox) →
- Should the agent be able to **transfer/forward to a human** during opening
  hours? If so, to what number, and when? →
- Who is the **point of contact** for the reservation system on your side? →

## 7. Reservation system (Libro) — for the developer, needs owner action  🔌

The agent is designed to plug into **Libro Reserve** (libroreserve.com), which we
understand YEN uses. Libro only grants API access to approved partners, so:

- Please confirm YEN's reservation platform is **Libro** (or tell us which one). →
- The owner (or us on your behalf, with your OK) needs to **email
  `admin@libroreserve.com`** to request partner/API access for YEN, including
  staging credentials. Are you OK with us initiating that? →
- Libro requires a **certification** step before production — expect this to take
  some back-and-forth. Until it's granted, the agent runs on our built-in mock,
  so development is not blocked.

> If YEN uses a **different** booking system (OpenTable, Resy, Tock, SevenRooms,
> a spreadsheet, or paper), tell us which — the agent is built to swap backends,
> and we'll target that instead.

## 8. Phone number & going live  ☎️  (later, when you're ready)

- Do you want the AI to answer your **existing** number, a **new** number, or
  only overflow when staff can't pick up? →
- Preferred area code for a new line if needed (514 / 438)? →
- Any hours when calls should go **straight to a human** instead of the AI? →

---

### Legal / disclosure note (informational)

The agent introduces itself as an **AI assistant** and always offers to take a
message or reach a person. Quebec/Canada consumer rules and Law 25 (privacy) may
apply to call recording and handling of personal data; we'll keep data handling
minimal (name + phone + reservation details only) and can review specifics with
you before launch.
