# Meeting Notes

## 03.11.2025

Agenda:

- Round of updates
- Deliverables for mid term (presentation & written report) (How are deviding the work there)
- Prepare question for Moritz
    1. How important is it that our app can ignore spelling mistakes in the input query? (not exact matches for names in general)
    2. Can we use APIs from other researches? e.g. <https://dblplink-2.skynet.coypu.org/api>
    3. Can we talk about AC-9 - what does "Context data is swappable" mean. Does this mean change in prompts or does this mean change of KG?
    4. Can we use other models (or local inf) or are we restricted to Ollama hosted models only? (API does not provide log probs) (AC-2)

---

Proposed prios:

1. First implement without fuzzy search
2. ES to make input more robust as extension

User query
-> mention extractio x - a person / paper / venue
-> entity linking loop
    -> **generate n candidates** for each match and rank them
    -> fuzzy search -> generate candidates
-> is ther a way to a have a "small index" (We can scope)
-> Can cricumvent this? "hack it"

---

1. Can we use APIs from other researches? e.g. <https://dblplink-2.skynet.coypu.org/api> (TBD)

---

1. Can we talk about AC-9 - what does "Context data is swappable" mean. Does this mean change in prompts or does this mean change of KG?

Not dependable on a single KG...
Code should be extendable!!!

Hinet: one KG for testing

---

1. Can we use other models (or local inf) or are we restricted to Ollama hosted models only? (API does not provide log probs) (AC-2)

Non locally "better".
Brainstorm
Can we use openai? TBD

---

Deliverables for mid term

a written requirements analysis report:

- Covering related work
- technical architecture
- recommendations
- detailed requirements specification

Presentation

- a presentation summarizing your key findings
- proposed technology stack
- software
- architecture and implementation roadmap

Julius + Mauri: Research on prompt construction and dataset generation and testability
Jeffry + Helik: Will research entity linking and proposals with code for generating scores
Wen: FE + dummy BE "dictator for architecture"

## 10.11.2025

### Notes

User: chooses domain -> upload context pack -> we generate queries to generate candidates on that specif KG
Context pack -> get right entities -> Query generation
How do you do use the context pack effectively?
Query -> Mention Extraction -> Entity Linking -> Return best entities -> FE display -> Query generation

Find out if it is:
    - possible
    - feasible
    - robust

---

### TODO

- [ ] Define a context pack structure for the specific case of DBLP + Sparql endpoint
- [ ] Test models to see which two work best. (We should document all the tests)
- [ ] Email about using opanai AND whether the UI needs to be chatbot style (chagpt style) or something like <https://dblplink-2.skynet.coypu.org/> would be enough.

### Questions

- Can we use the current tools to generate a test set for our pipeline? (Yes?)

## 17.11.2025

Questions:

- [ ] Chatbot style UI? (did not ask but did not seem to be an issue)
- [ ] Open AI budget? What would we need it for?

Notes:

- Ideally no paid APIs since no budget
- acceptance criteria, ranked them, see which ones are interlinked
- Stakeholders? Who are the users?
- Proposed tech stack
- What have we noticed? About time and calls... include in the report.
- Limiting constraints

## 15.12.2025

ALL: Need context pack

We decide input context will be endpoint, rdf schema and tbd examples.

- Mention Extraction
- Candidate Generation
- Candidate Ranking
- Query Generation

Missing:

- **Choose relevant context based on input question & task**
- Candidate Generation - Borken
- Candidate Ranking - Broken

- SMALL DIFFERENT KG FOR TESTING (which has RDF SCHEMA + ENDPOINT (can be local) + EXAMPLES (can be manual))

Jeffry will push context pack v1, fix candidate generation and ranking # after this can also look into context selection
Julius will try to integrate into the query generation pipeline
After he finishes the pipeline -> look into context selection

root_nodes = [
    "dblp:Creator".
    "dblp:Publication",
    "dblp:Stream",
]

def list_prop(node: str) -> list[str]:
    return []

Step1 :
Gvie root_nodes to llm and function

resp = await client.chat(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": q}
        ],
        tools=[list_prop]
    )

for call in resp.tool_calls:
    # Call the function
    # append results to context
    # call llm again with updated context

LLM: I want to use: list_prop with args: {node: "dblp:Creator"}

## 12.01.2026

Next Steps:

- move into modules

On the python SchemaIndex:
RDF <-> query string
ON RDF perfom traversal and filtering
why do we need the extra python object layer

RDF, XML -> schema agnostic <-

Is our object expressive enough? Are we missing anything?

Document decisions - why did we make them; try not to reinvent the wheel

Also:

- Add graph of where LLM calls happen in the report (visual explanation of pipeline)

Questions:

- Tests: How big should our test set be? (for testing the whole pipeline)
    Have the main problems covered.
    Depth: how many edge cases? No definite answer.

    Plan: Have queries of different types for 2 different KGs (different domains)

## 19.1.2026

Goal next week: backend ready for conencting with frontend

Round of updates:
    - Julius: Demo for query generation working with function calling!
    - Jeffry: Was lazy this week.
    - Wens: still on vacations
    - Helik: Found sveral KGs that are not scholarly; Mention extraction is not working on Golem object example. Should we create a loop for mention extraction for top 3 results? Learning pytest.
    - Mau: Catching up.

Do we have questions for Moritz? No. Just update.

What are we gonna do till next?
    - Julius: implement modules internal/file.py and routers/usecase.py with fastapi for query generation.
    - Jeffry: v1 Routers for mention extraction (show detected spans? No; mentions with candidates and scores)
    - Wens: Catch up on code + work with Jeffry
    - Helik: Decide on testing KGs + setup pytest (does not mean write extensive tests); Checkout GLiNER (not prio A).
    - Mau: Catch up + help Julius

## 26.1.2026

We all have got working setup.

Update round:

- Jeffry: mention integrated in backend and setup tests
- Mauri+Julius: worked on query generation
- Wens: Read codebase. Fix FE code. Merge types BE/FE.
    Discuss: What do we want to present the user?
- Helik: Experimented with GLiNER. Pokemon endpoint setup. Play with pytest. Think about eval setup.

Sync with Moritz:

- Have you started on the report???
- Advice: Setup structure and what you want to mention!
- Description of the problem, goal
- Explain the system
- scientific report that could published

Next steps:

- Clean Rrepo root (done)
- W Discuss: What do we want to present the user?

Todo for next week:

- Helik: Docker compose to fuseki; work on evaluation setup
- Jeffry: Setup report basic formatting on repo (sync with Helik on evals for mentions)
- Julius + Mauri: Get query generation backend ready for FE (tests)
- Wens: Connect FE to BE for mention extraction

## 02.02.2026

Updates:

- Julius + Mauri: Query generation backend ready for FE (tests)
- Jeffry: Report basic formatting on repo (sync with Helik on evals for mentions)
- Helik: Docker compose to fuseki; work on evaluation setup
- Wens: Schema list available in FE components
  - estmate not a lot of work but FE has become complicated

Open issues:

- (EL) Some graphs do have properties with range string & use rdfs:label without putting it in the schema
  - <pikachu_iri> rdfs:label "Pikachu" // <- not in schema
  - <some_guy> dblp:CreatorName "Some Guy" // <- in schema
- (EL) Kontext pack needs to support more owl features
- (QG) How do we evaluate the generated queries?
  - Check SPARQL (not very easy to do deterministic evals)
  - Check results <-
  - Most expensive way -> would be let llm judge

Missing:

- Route in BE to validate and execute query against endpoint

Next steps:

- Mauri + Julius: Think about eval for query generation
- Jeffry: Fix docker image
- Wens: Upload Schema, display BE data (schema, mentions, query)
- Helik: Generate gold dataset for dblp (check if we can hack a samrt llm to do one for us)

Questions Moritz:

- (EL) Some graphs do have properties with range string & use rdfs:label without putting it in the schema
- Latex report - is any template preferred? - min/max pages? ~8 (max 10 pages)

Notes:

- Reminder: Submissiong dates 11.3 report /. 16.3 presentation

```python
class LinkedMention(BaseModel):
    text: str  # Ties it back to query
    type: str  # Might be useful for querying
    label_pred: Optional[str]
    attrs: Dict[str, str] = Field(default_factory=dict)
    candidate: Candidate
```

## 09.02.2026

## Update Round

- Julius + Mauri:
  - Pydantic model for query generation (removed examples for now)
  - Adding examples is still open
  - Linked Mentions defintion
  - Started implementing run query module

- Wens: Connect Mention Linking Backend
  - Question: Why does it not return mention? A: We do not handle typos :(

- Helik
  - Owl restrictions addition
  - Started with pokemon eval dataset
  - Updated the candidate query generation to order by exact matches and also filter non-English langauge tags

- Jeffry (evaluate mention extraction on DBLP)

## Next Steps

- Julius + Mauri:
  - Start testing (after Thu.)
- Wens connect sparql query generation backend
- Helik: Work on dataset generation
- Jeffry: Pick a problem and try to fix it

## Update Jeffry

EL evaluation snapshot (DBLP-QuAD, 50 random queries, processed entities):

- Summary from `./backend/evaluation/runs/dblp-quad/20260205-211817/results.json`:
  - `gold_entities_total=60`
  - `gold_entities_hit=44` (`recall@10 = 0.733`)
  - `gold_entities_top1=39` (`top1 = 0.650`)
  - `gold_entities_not_retrieved=14`
  - `gold_entities_retrieved_not_top1=5`
- One run item failed due endpoint connectivity (`ConnectError`), so 2 gold entities are missing `gold_analysis` in this run.

Diagnostic breakdown (retrieval vs reranker):

- Output on this run:
  - `retrieval_failures=14` (dominant bottleneck)
  - `rank_histogram_retrieved={1:39, 2:3, 3:2}`
  - `reranker_decision_cases=8` (only cases with >=2 candidates)
  - `reranker_not_top1_in_decision_cases=5` (misses at ranks 2/3 only)
  - `no_choice_cases_below_min_candidates=36` (reranker had 0/1 candidate, so not a ranking problem)

Observed failure patterns:

- Frequent retrieval misses on abbreviated/ambiguous person names (e.g., initials, partial names, punctuation variants).
- Many misses have empty candidate lists or only one candidate, so ranking cannot recover.

Priority actions for next iteration:

- Improve candidate generation fallback for names:
  - initials-aware and punctuation-robust matching
  - token-drop / longest-token fallback when no candidates
- Add retry logic for transient endpoint/network errors in eval runs.
- Re-run same seed after candidate-gen changes and compare:
  - `gold_entities_not_retrieved`
  - `gold_retrieved_rate_micro`
  - `reranker_decision_cases` and `reranker_top1_rate_in_decision_cases`

## Update Julius

- added evaluation logic: check if results from generated query are a superset of the expected query
  - so far only for dblp quad
- processed some data from the dblp quad dataset, similiar to what jeffrey did
  - venue IRIs where missing in the Boolean queries as well
- Changed tools, to be more token efficent
  - list_classes
  - describe_class
  - get_outgoing_properties
  - get_incoming_properties
  - validate_sparql

- Problem: dblp (and maybe other KGs) doesnt use Reasoners for owl inference
  - authorOf does not exist in the data KG but in the schema, only authoredBy is used
  - how can the llm get that information?
- Backend context pack, mixup with endpoint URL (example.org for dblp)

- ask moritz for more context window?

*Next Steps*:

- change test setup to work with dblp_sparql_gold (so it includes class,label of linked mention)
- add examples in context pack and prompt construction
- add support to test other datasets in analyze query construction
- write Report
- Support for booleans in query response
- eval check that same amount of solutions

## Update Helik

- changed candidate generation query to include node degree as a criteria of importance for better matching, also handling dot/period in the end
- generated more entries in gold pokemon dataset
- handling of names in various formats in the input query string via token-based matching and using regex

*Next Steps*:

- Work on ranking the candidates
- Change pokemon gold format to be more compatible with the current eval loop
- Merge the pokemon graph into one big union graph so that FROM clause is not required
- Update the project management files mainly Gantt chart from the meeting report

### Meeting (23/02)

- for rdfs:label issue, it seems to be specific to Pokemon KG and we can deprioritize it for the time-being
- Can use the newly added RWTH GPT at <https://help.itc.rwth-aachen.de/en/service/1808737e10424937b76e564ed15d8028/article/4f07ebbbc8c4477a8db9baa441494941/> and see if it works better than warhol ollama server. But doesn't have all models.
- Have communicated for adding newer models in warhol server
- Report should be focussing on mainly research and less about project management stuff
- If needed, they can arrange a commercial setup. If needed, we have to calculate the budget (eg. number of tokens etc) and communicate to them
- We can send the docker file once done to be hosted (group 1 has hosted already). For that we also need to add description on how to use etc. and also put up a survey asking for feedback.

### Meeting (26/02)

Notes from meeting with Julius and Helik from Jeffry:

- missing examples FE/BE
- DBLP problem with query generation - what to do authorOf missing...
- Evaluation 5 questions from each type. Wrong ones
- Julius ideally we finish everything next week (Jeffry likes that)
- Add google form to FE for feedback before passing for hosting
- Missing Report and presentation
- Potential things high impact:
  - Run query tool llms
  - subset of allowed queries (FE?, BE)
  - Raise errors and show to user
  - Example FE / BE
  - Report Structure

Open questions:

- API key for hosting?
- What will be the hosting url for the BE - so we can put in the FE
- AC-18 Discuss next week

## Meeting (02/03)

TODO:

- Tool loop error
- Do not show examples for non pokemon or dblp
- [ ] **AC-17** Validates that prefixes resolve and that properties/classes in the query exist (via schema/context or endpoint introspection); reports actionable errors.
- Evaluation
  - Query gen
  - Entity linking
- Report
- Presentation

### Draft Feedback

- Related work instead of Lit Review
- Mention in the final report - use of examples (how to)
- Future work - session persistence ... connect to external database, authentication, role management
- list models from api for FE as well (instead of hardcoding)

### Open questions

- [x] **AC-3** Clear module boundaries for: **mention extraction**, **entity linking**, prompt builder, generator, validator, executor; interfaces documented. (backend code!!!)

- [ ] **AC-4** Configuration files define model(s), endpoint, context pack, and allowed SPARQL subset; reload via restart or hot-reload. Optional over the web interface.
  - SPARQL SELECT, DESCRIBE, ASK enforced but not configurable since it does not make sense

- [ ] **AC-10** If DBLP is chosen: the pack includes IRIs for core scholarly concepts (author, publication, venue/workshop, year) and at least 10 DBLP-specific example queries.
  - limit num examples

- [x] **AC-11** Devise a feedback loop to fix possible errors in IRI entity linking.
  - you can choose another candidate
  - we can give a hint to re write the query if the results are poor
- [ ] **AC-12** Implement strategies for detection and adjustment of incorrect NEL results or used IRIs in the queries.
- Ideal solution was a chat with more of an agentic UI

- [ ] **AC-17** Validates that prefixes resolve and that properties/classes in the query exist (via schema/context or endpoint introspection); reports actionable errors.

- API key for hosting? -> for now use Jeffry's
- What will be the hosting url for the BE - so we can put in the FE -> pass compose file for hosting

- Wikidata - good we ignored, explain in the report

### Open

- SPARQL subset

## 04.03.2026

### Goal for today?

- Get project ready for submission -> final code, merged, tested and evaluated
- Report start and at least have a structure and some content for each section and solid plan for finishing it in the next two days.

### Missing

- (High) Merge branches and sync codebase
- (High) Dataset work
- (High) Adjust examples on FE
- (High) Fix timeout error on REST calls
- (High) Explore why llms get stuck in tool call loops and try to fix
  - We should assume in the future there will better models and we will not write **weird** scaffolding to fix this
- (High) Report writing - agree on rough content per section, assign sections?
- (Low) Presentation?
- (Medium?) Finish chat mvp

### TODO next 2h

- Jeffry: Finish the mvp so that we can merge it and have one branch
- Helik: Dataset work
- Julius: Report + loop error exploration
- Mauri: Report + loop error exploration
- Wens:
  - Adjust examples for the FE (they makes sense, are varied (different types, ask/select, venue year, aggregation, ask for specific columns) and work most of the time)
  - Fix timeout error on REST calls
  - Move .env to root

## 09.03.2026

### Still cooking

- Helik is running some evals
- Julius as well (82%+)

### Questions

- Report feedback
- Duration of presentation
  - is it bad if some people talk more than others?
- Is it ok to use our own laptop and do a live demo?
- Slide submission is wednesday - are we allowed to update them after the submission?
- Did you have trouble deplying the docker compose?
- Can we link the code?

### Note

- Duration 15 + 10 Q&A
- We can update eval data up to the presentation 🎉
- Feedback of the report tomorrow
- Quick note: DBLP-QuAD did we reference it before hand? be sure to reference it properly (cite the paper)
- Somewhat balanced talking -> Prepare for questions ;)
- Demo is fine. Maybe have a backup video jic.
- Cosmetic changes are fine but no major changes should be made.
- As link to code
- Checkout out the other teams results
