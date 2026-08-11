## How to set up the project?

### Frontend


- Installation
    - Prereqs: Node.js (v18+ recommended), npm or any npm-like tool
    - Navigate to the frontend directory: `cd frontend`
    - Install dependencies: `npm install` (or `pnpm install`)

- Start server
    - Dev server: `cd frontend && npm run dev`
    - Build: `cd frontend && npm run build` then `npm start`

### Backend

- Installation
    - Prereqs: Python 3.10+, virtualenv or venv recommended
    - Navigate to the backend directory: `cd backend`
    - Create and activate a virtual environment: `python -m venv venv && source venv/bin/activate`
    - Install dependencies: `pip install -r requirements.txt`
    - For development extras: also run `pip install -r requirements-dev.txt`

- Start server
    - Dev with auto-reload: `uvicorn src.main:app --reload`


## Dev

### Frontend

- Where should I start? 
    - `frontend/src/app/page.tsx`
    - This file contains the root layout and home page component. The page imports custom components from components.
    - Take few minutes to check the home page component with **seven pipeline steps**. (Have a look on how to write react code. It might help.)
    - It is good to know which **API endpoints** get called somewhere/somehow
- Understanding the UI library
    - How to add ui component: https://ui.shadcn.com/docs/installation/next  
    - Visit https://ui.shadcn.com/docs/components to find the component you need 
    - Run `npx shadcn-ui@latest add <component-name>` from the frontend directory
    - The component will be added to ui and is ready to import and use
    - Example: `npx shadcn-ui@latest add dialog` adds a Dialog component
        - Added components will be located at `frontend/src/components/ui`.
- What are those defined components in `frontend/src/components`?
    - Custom project components are in components and include:
        - `entity-table.tsx`: displays extracted entities in table format
        - `mention-card.tsx`: renders mention information as cards
        - `mention-instruction.tsx`: provides UI for mention input or instructions
        - `query-results.tsx`: displays query execution results
        - `question-card.tsx`: displays questions to the user
        - `sparql-editor.tsx`: editor interface for SPARQL queries
        - `text-input.tsx`: reusable text input component
- What's next?
    - [ ] Handle error gracefully  
    - [ ] Switch/Upload context somewhere/somehow  

### Backend

- Where to start?
    - The main entry point is `backend/src/main.py`. This file initializes the FastAPI application and registers all routers
    - The app runs on `http://localhost:8000` by default
    - You may want to check following files:
        - `backend/src/routers/demo`: demo-specific routes
            - `mention.py`: mention extraction endpoints
            - `generate.py`: generation endpoints
            - `query.py`: query execution endpoints
    - demo-data: sample data files for testing (e.g., `mention_extraction_demo.json`, `result-demo.json`)


- What's next?
  - [ ] How to handle context pack (upload/switch/update etc.)?
  - [ ] Integrate pipelines written in notebooks into new routers. 
    - Use the same API endpoints (without `demo`) in `backend/src/routers/demo`
    - Check the input and output of the endpoints. It may need to negotiate
        ```python
        class Entity(BaseModel):
            mention: str
            mention_type: str
            selectedItem: dict


        class SPARQLGenerationRequest(BaseModel):
            text: str
            entities: list[Entity]
            model: str

        @router.post("/generate", status_code=status.HTTP_200_OK)
        async def generate_sparql(request: SPARQLGenerationRequest):

            # YOUR CODE
            sparql_query = "GENERATED SPARQL CODE"

            return {"sparql_query": sparql_query, "model": request.model}
        ```