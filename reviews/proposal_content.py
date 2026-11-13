# Demo proposals for local testing. Replace with Moodle uploads later.

PROPOSALS = {
    "Team A": {
        "title": "Campus Shuttle Helper",
        "keywords": "campus mobility, public timetable, retrieval",
        "abstract": (
            "A student standing at a HKU stop asks when the next usable shuttle "
            "leaves and whether it serves their destination. The system answers "
            "only from a curated public timetable, cites the row it used, and "
            "refuses emergency or accessibility-routing questions."
        ),
        "body": """User & task
A current HKU student at a named stop wants the next two departures that reach a named campus destination, with the source timetable row shown.

Does not
No live GPS, no emergency routing, no accessibility path planning, no medical advice.

Data
Public shuttle PDF/HTML timetable for one semester. Licence: public campus notice. We will store a dated snapshot and refuse queries about unpublished changes.

Core workflow
1. Parse the stop and destination from a short question.
2. Retrieve matching rows from the snapshot.
3. Return the next two times plus a citation (table, stop name, effective date).
4. If the stop or destination is missing, say so and stop.

Evaluation
Ten held-out questions with gold stop/destination/time. Score exact time match and whether the cited row is the one used. Two refusal cases (emergency; unpublished stop) must refuse.

Team note
This is a demo proposal for AILT9019 W5 peer review. Treat it as a real submission when scoring.
""",
        "pdf_lines": [
            "User: HKU student at a named stop.",
            "Task: next two shuttles to a named destination, with citation.",
            "Data: public semester timetable snapshot.",
            "Does not: GPS, emergency routing, accessibility paths.",
            "Eval: 10 timetable questions + 2 refusals.",
        ],
    },
    "Team B": {
        "title": "Course Policy Explainer",
        "keywords": "policy Q&A, citation, refusal",
        "abstract": (
            "A student asks a plain-language question about a fixed set of public "
            "course policies. The system answers only from those pages, quotes the "
            "paragraph it used, and refuses personal-case or appeal questions."
        ),
        "body": """User & task
A student in this course wants a short answer to a policy question (late work, attendance, AI-use rules) with a paragraph citation.

Does not
No personal-case interpretation, no grade appeals, no advice about other courses, no invented rules.

Data
The public Course Overview and Week 1-2 policy pages only. We will freeze a dated copy. If a question is not covered, the system says the document does not say.

Core workflow
1. Retrieve two candidate paragraphs from the frozen pages.
2. Answer in at most five sentences and quote the supporting sentence.
3. If neither paragraph supports an answer, refuse.

Evaluation
Twelve questions with gold answers and required citations. Score answer correctness and citation match. Three personal-case prompts must refuse.

Team note
This is a demo proposal for AILT9019 W5 peer review. Treat it as a real submission when scoring.
""",
        "pdf_lines": [
            "User: student asking about this course's public policies.",
            "Task: short cited answer, or a refusal.",
            "Data: frozen Course Overview + early-week policy pages.",
            "Does not: personal cases, appeals, other courses.",
            "Eval: 12 QA items + 3 refusal prompts.",
        ],
    },
    "Team C": {
        "title": "Recycling Rules Helper",
        "keywords": "municipal rules, lookup, public guidance",
        "abstract": (
            "A resident of one named Hong Kong district asks which bin a listed "
            "household item should go in. The system looks up a published recycling "
            "guide and returns the bin plus the sentence it used."
        ),
        "body": """User & task
A resident of one named district wants to know which published bin (recyclable / general / other) a named household item belongs in, with a citation.

Does not
No hazardous-waste disposal advice, no business/commercial waste, no legal interpretation.

Data
One public district recycling FAQ or poster set, snapshotted with the access date. Items not in the guide are reported as not listed.

Core workflow
1. Map the user item to a row in the snapshot (exact or listed synonym).
2. Return the bin label and the quoted rule sentence.
3. If unlisted, say the guide does not list the item.

Evaluation
Fifteen items from the guide (correct bin + citation) and five unlisted items (must say unlisted). No extra browsing.

Team note
This is a demo proposal for AILT9019 W5 peer review. Treat it as a real submission when scoring.
""",
        "pdf_lines": [
            "User: resident of one named district.",
            "Task: which published bin for a named household item.",
            "Data: one public recycling FAQ snapshot.",
            "Does not: hazardous waste, commercial waste, legal advice.",
            "Eval: 15 listed items + 5 unlisted refusals.",
        ],
    },
    "Team D": {
        "title": "Housing Rules Navigator",
        "keywords": "housing, hall rules, citation",
        "abstract": (
            "A hall resident asks whether a common action (guest hours, cooking, "
            "quiet hours) is allowed under one published hall handbook. The system "
            "quotes the clause and refuses roommate-dispute or legal questions."
        ),
        "body": """User & task
A resident of one named hall wants a yes/no/unclear answer about a handbook topic, with the clause quoted.

Does not
No roommate mediation, no tenancy-law advice, no advice for other halls, no emergency procedures.

Data
One public hall handbook PDF, snapshotted. Only sections on guests, cooking, and quiet hours are in scope for the prototype.

Core workflow
1. Classify the question into guests / cooking / quiet hours / other.
2. Retrieve the matching clause.
3. Answer yes, no, or not stated, and quote the clause.
4. Other topics refuse.

Evaluation
Ten handbook questions with gold labels and clause IDs. Four off-scope prompts must refuse.

Team note
This is a demo proposal for AILT9019 W5 peer review. Treat it as a real submission when scoring.
""",
        "pdf_lines": [
            "User: resident of one named hall.",
            "Task: yes/no/not-stated on guests, cooking, or quiet hours.",
            "Data: one public hall handbook snapshot.",
            "Does not: disputes, law, other halls, emergencies.",
            "Eval: 10 in-scope questions + 4 refusals.",
        ],
    },
}
