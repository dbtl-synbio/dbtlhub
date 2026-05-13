import os
import json
import requests
import pandas as pd
from time import sleep
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_URL = "https://bio.tools/api/tool/"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ror_cache.json")

# -----------------------------
# Session
# -----------------------------

def _make_session(timeout=45):
    """Create a requests Session with retry logic and a default timeout."""
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.request = lambda method, url, **kw: requests.Session.request(
        session, method, url, timeout=kw.pop("timeout", timeout), **kw
    )
    return session


# -----------------------------
# bio.tools fetcher
# -----------------------------

def get_all_tools(max_pages=None, sleep_time=0.3, timeout=45):
    session = _make_session(timeout=timeout)
    page = 1
    dfs = []

    while True:
        url = f"{API_URL}?format=json&page={page}"

        try:
            resp = session.get(url, timeout=timeout)
        except requests.exceptions.Timeout:
            print(f"  [TIMEOUT] page {page} — skipping and stopping.")
            break
        except requests.exceptions.ConnectionError as e:
            print(f"  [CONNECTION ERROR] page {page}: {e} — stopping.")
            break

        if resp.status_code != 200:
            print(f"Stopping at page {page} (status {resp.status_code})")
            break

        data = resp.json()
        tools = data.get("list", [])

        if not tools:
            break

        dfs.append(pd.DataFrame(tools))
        total = data.get("count", "?")
        print(f"Fetched page {page} ({len(tools)} tools) — total in API: {total}")

        page += 1
        if max_pages and page > max_pages:
            print(f"Reached max_pages={max_pages}, stopping.")
            break

        if data.get("next") is None:
            break

        sleep(sleep_time)

    if not dfs:
        raise RuntimeError("No data was fetched. Check your internet connection or the bio.tools API status.")

    return pd.concat(dfs, ignore_index=True)


# -----------------------------
# ROR country lookup
# -----------------------------

_ror_cache = {}

def load_cache():
    global _ror_cache
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            _ror_cache = json.load(f)
        print(f"Loaded {len(_ror_cache)} cached ROR lookups.")

def save_cache():
    with open(CACHE_FILE, "w") as f:
        json.dump(_ror_cache, f, indent=2)
    print(f"Saved {len(_ror_cache)} ROR lookups to cache.")

def lookup_ror_country(institution_name: str, timeout=10) -> str:
    """Query the ROR API to get the country of an institution by name."""
    if not institution_name.strip():
        return ""

    url = "https://api.ror.org/organizations"
    params = {"affiliation": institution_name}

    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", [])
        if not items:
            return ""

        # Take the best match only if ROR flagged it as confident
        best = items[0]
        if best.get("chosen"):
            org = best.get("organization", {})
            return org.get("country", {}).get("country_name", "")

        return ""

    except (requests.exceptions.RequestException, KeyError, IndexError):
        return ""

def get_country_cached(institution_name: str) -> str:
    if institution_name not in _ror_cache:
        _ror_cache[institution_name] = lookup_ror_country(institution_name)
        sleep(0.1)  # polite delay to the ROR API
    return _ror_cache[institution_name]


# -----------------------------
# Feature extraction
# -----------------------------

def extract_language(tool):
    lang = tool.get("language", [])
    if isinstance(lang, list):
        return ", ".join([str(l) for l in lang if l])
    return str(lang) if lang else ""


def extract_type(tool):
    t_type = tool.get("toolType", [])
    if isinstance(t_type, list):
        return ", ".join([str(t) for t in t_type if t])
    return str(t_type) if t_type else ""


def extract_topics(tool):
    topics = tool.get("topic", [])
    topic_terms = []
    for t in topics:
        if isinstance(t, dict) and t.get("term"):
            topic_terms.append(t.get("term"))
    return ", ".join(topic_terms)


def extract_input_output(tool):
    inputs = []
    input_formats = []
    outputs = []
    output_formats = []

    for func in tool.get("function", []):
        for inp in func.get("input", []):
            data = inp.get("data")
            if isinstance(data, dict) and data.get("term"):
                inputs.append(data.get("term"))
            for fmt in inp.get("format", []):
                if isinstance(fmt, dict) and fmt.get("term"):
                    input_formats.append(fmt.get("term"))

        for out in func.get("output", []):
            data = out.get("data")
            if isinstance(data, dict) and data.get("term"):
                outputs.append(data.get("term"))
            for fmt in out.get("format", []):
                if isinstance(fmt, dict) and fmt.get("term"):
                    output_formats.append(fmt.get("term"))

    inputs = list(dict.fromkeys(inputs))
    input_formats = list(dict.fromkeys(input_formats))
    outputs = list(dict.fromkeys(outputs))
    output_formats = list(dict.fromkeys(output_formats))

    return inputs, input_formats, outputs, output_formats


def extract_country(tool, use_ror=True) -> str:
    # 1. ElixirNode first — clean and direct
    nodes = tool.get("elixirNode", [])
    if nodes:
        return ", ".join(nodes)

    # 2. Credit institutions via ROR
    if use_ror:
        countries = []
        for credit in tool.get("credit", []):
            name = (credit.get("name") or "").strip()
            if name:
                country = get_country_cached(name)
                if country and country not in countries:
                    countries.append(country)
        if countries:
            return ", ".join(countries)

    # 3. Raw institution names if ROR found nothing
    raw = [c.get("name", "") for c in tool.get("credit", []) if c.get("name")]
    return ", ".join(raw) if raw else ""


# -----------------------------
# DBTL classification
# -----------------------------

EDAM_DBTL = {
    # ── Design ───────────────────────────────────────────────────────────────
    "topic_2275": "Design",  # Molecular modelling
    "topic_1775": "Design",  # Protein design / function
    "topic_0082": "Design",  # Structure prediction
    "topic_0154": "Design",  # Small molecule design
    "topic_3895": "Design",  # Synthetic biology
    "topic_3880": "Design",  # Metabolic engineering
    "topic_3307": "Design",  # Computational biology
    "topic_0160": "Design",  # Sequence sites, features and motifs
    "topic_3314": "Design",  # Chemistry
    "topic_0797": "Design",  # Protein structure comparison
    "topic_3068": "Design",  # Literature and language
    "topic_2259": "Design",  # Systems biology

    # ── Build ────────────────────────────────────────────────────────────────
    "topic_3070": "Build",   # Biology
    "topic_3372": "Build",   # Software engineering
    "topic_0196": "Build",   # Sequence assembly
    "topic_3053": "Build",   # Genetic engineering
    "topic_3912": "Build",   # Nucleic acid design (oligos, primers)
    "topic_3168": "Build",   # Sequencing (library prep / NGS)

    # ── Test ─────────────────────────────────────────────────────────────────
    "topic_3308": "Test",    # Transcriptomics
    "topic_0203": "Test",    # Gene expression
    "topic_0121": "Test",    # Proteomics
    "topic_3172": "Test",    # Metabolomics
    "topic_0625": "Test",    # Phenotype
    "topic_3365": "Test",    # Data quality management
    "topic_3391": "Test",    # Omics
    "topic_3360": "Test",    # Biomarkers
    "topic_0654": "Test",    # DNA mutation / variant calling
    "topic_0085": "Test",    # Functional genomics
    "topic_3520": "Test",    # Proteomics experiment
    "topic_0092": "Test",    # Data visualisation

    # ── Learn ─────────────────────────────────────────────────────────────────
    "topic_3474": "Learn",   # Machine learning
    "topic_2269": "Learn",   # Statistics and probability
    "topic_0219": "Learn",   # Data submission, annotation and curation
    "topic_3321": "Learn",   # Computational chemistry
    "topic_3318": "Learn",   # Physics
    "topic_0091": "Learn",   # Bioinformatics
    "topic_3489": "Learn",   # Data integration and warehousing
    "topic_3071": "Learn",   # Data management
}


def _edam_id(uri: str) -> str:
    return uri.rstrip("/").rsplit("/", 1)[-1]


def classify_dbtl(tool: dict) -> dict:
    phases = {"Design": 0, "Build": 0, "Test": 0, "Learn": 0}
    for topic_entry in tool.get("topic", []):
        uri = topic_entry.get("uri", "")
        edam_id = _edam_id(uri)
        phase = EDAM_DBTL.get(edam_id)
        if phase:
            phases[phase] = 1
    return phases


# -----------------------------
# Special flags
# -----------------------------

def detect_sequence_input(inputs):
    return int(any("sequence" in str(i).lower() for i in inputs))

def detect_protein_output(outputs):
    return int(any("protein structure" in str(o).lower() for o in outputs))


# -----------------------------
# Main processing
# -----------------------------

def build_dataset(df):
    records = []

    for _, tool in df.iterrows():
        inputs, input_formats, outputs, output_formats = extract_input_output(tool)
        dbtl = classify_dbtl(tool)

        record = {
            "Tool": tool.get("name"),
            "Type": extract_type(tool),
            "Topic": extract_topics(tool),
            "Language": extract_language(tool),
            "Input": ", ".join(inputs),
            "Format input": ", ".join(input_formats),
            "Output": ", ".join(outputs),
            "Format output": ", ".join(output_formats),
            "Design": dbtl["Design"],
            "Build": dbtl["Build"],
            "Test": dbtl["Test"],
            "Learn": dbtl["Learn"],
            "Country/Node": extract_country(tool, use_ror=True),
            "Sequence (i)": detect_sequence_input(inputs),
            "Protein structure (o)": detect_protein_output(outputs),
        }
        records.append(record)

    result_df = pd.DataFrame(records)

    dbtl_cols = ['Design', 'Build', 'Test', 'Learn']
    result_df['In_DBTL_Cycle'] = result_df[dbtl_cols].any(axis=1).astype(int)

    # ── Multi-phase combinations ──────────────────────────────────────────────
    D = result_df['Design']
    B = result_df['Build']
    T = result_df['Test']
    L = result_df['Learn']

    # Pairs
    result_df['DB']  = (D & B).astype(int)
    result_df['DT']  = (D & T).astype(int)
    result_df['DL']  = (D & L).astype(int)
    result_df['BT']  = (B & T).astype(int)
    result_df['BL']  = (B & L).astype(int)
    result_df['TL']  = (T & L).astype(int)

    # Triples
    result_df['DBT'] = (D & B & T).astype(int)
    result_df['DBL'] = (D & B & L).astype(int)
    result_df['DTL'] = (D & T & L).astype(int)
    result_df['BTL'] = (B & T & L).astype(int)

    return result_df


# -----------------------------
# Run
# -----------------------------

if __name__ == "__main__":
    load_cache()  # load any previous ROR lookups from disk

    print("Downloading bio.tools data...")
    # Set max_pages=2 to do a quick test before pulling everything
    df_raw = get_all_tools(
        max_pages=None,   # None = fetch all pages
        sleep_time=0.3,   # polite delay between requests
        timeout=45,       # seconds before giving up on a single request
    )

    print(f"Downloaded {len(df_raw)} tools. Processing dataset...")
    df_final = build_dataset(df_raw)

    save_cache()  # persist new ROR lookups so next run is faster

    out_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bio_tools_dbtl_6.csv")
    print(f"Saving to {out_file}...")
    df_final.to_csv(out_file, index=False)

    print(f"Done! {len(df_final)} tools saved to {out_file}")