### Step 1

Install doccana (pip or docker)
Create a project
Create a text file with queries
Import in doccana and annotate manually
Export data as all.jsonl (it is in zip file)
Manually split into train.jsonl and dev.jsonl

### Step 2

Use the script convert_data.py to convert train.jsonl and dev.jsonl into spacy compatible train.spacy and dev.spacy

### Step 3

Need to have : pip install spacy-transformers

directory structure
your_project/
├─ data/
│  ├─ train.spacy
│  └─ dev.spacy
├─ configs/
│  └─ config.cfg
├─ scripts/
│  └─ convert_doccano_to_spacy.py
├─ training/
│  ├─ model-best/
│  ├─ model-last/
│  └─ metrics.json
├─ notebooks/
├─ README.md
└─ .gitignore

### Step 4

(All from root (main) folder)

Generate config file:
python -m spacy init config configs/config.cfg --lang en --pipeline transformer,ner --optimize accuracy

Validate data:
python -m spacy debug data configs/config.cfg --paths.train data/train.spacy --paths.dev data/dev.spacy

Train (If have gpu use -g 0):
python -m spacy train configs/config.cfg --output training --paths.train data/train.spacy --paths.dev data/dev.spacy -g 0

Evaluate
python -m spacy evaluate training/model-best data/dev.spacy --output training/metrics.json

Load for inference

import spacy
nlp = spacy.load("training_trf/model-best")
doc = nlp("list authors of paper Attention is all you need")
print([(ent.text, ent.label_) for ent in doc.ents])
