import importlib

PROMPTS_DIR = importlib.resources.files("src.prompts")


def load_prompt(*descendants: str) -> str:
    prompt_path = PROMPTS_DIR
    for d in descendants:
        prompt_path = prompt_path.joinpath(d)
    with prompt_path.open("r") as f:
        return f.read()


def replace_prompt_vars(prompt: str, vars: dict) -> str:
    out = prompt
    for k, v in vars.items():
        out = out.replace(f"{k}", v)
    return out


MENTION_EXTRACTION_PROMPT = load_prompt("mention_extraction.md")
QUERY_CONSTRUCTION_PROMPT = load_prompt("query_generation_2.md")
MENTION_AGENT_SYSTEM_PROMPT = load_prompt("mention_agent_system.md")
