# --- Search queries ---
SEARCH_QUERIES = [
    {"term": "python developer", "location": "Barcelona"},
    {"term": "PHP developer", "location": "Barcelona"},
]

RESULTS_PER_QUERY = 100
HOURS_OLD = 24  # Solo ofertas de las últimas 24h

# --- Hard filters ---
EXCLUDE_TITLE_KEYWORDS = [
    "junior", "intern", "internship", "prácticas", "becario",
    "frontend", "front-end", "manager", "lead",
    "mobile", "ios", "android", "data scientist", "machine learning", "consultora"
]

BLACKLIST_COMPANIES = [
    # Añade empresas que quieras ignorar
]

MIN_SALARY_YEARLY = 35000  # EUR, ignorado si la oferta no indica salario

# --- Keyword scoring ---
CORE_STACK = [
    "python", "php", "django", "flask",
    "rest api", "microservices", "microservicios", "api rest",
    "symfony", "hexagonal", "clean architecture", "event-driven",
    "cqrs", "domain-driven design", "ddd", "event sourcing",
    "tdd", "test-driven development",
]  # +3 puntos cada uno

SECONDARY_STACK = [
    "docker", "kubernetes", "redis", "mongodb", "mongo", "node.js", "nodejs",
    "ci/cd", "ci cd", "github actions", "rabbitmq", "kafka", "java", "spring boot",
    "laravel",  "sql", "postgresql", "mysql", "jenkins", "react", "typescript",
]  # +2 puntos cada uno

BONUS_STACK = [
    "agile", "scrum", "terraform", "gcp", "cloud", "severless"
]  # +1 punto cada uno

MIN_KEYWORD_SCORE = 4  # Mínimo para pasar al triaje de Claude

# --- Claude triage ---
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_SCORE_THRESHOLD = 7  # Mínimo para notificar por Telegram
