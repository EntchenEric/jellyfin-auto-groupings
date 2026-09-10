import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

FRANCHISE_RULES = {
    "Marvel Cinematic Universe": [r"\bmcu\b", r"marvel cinematic universe", r"avengers", r"iron man", r"thor", r"captain america"],
    "Star Wars": [r"star wars", r"\bsw\b"],
    "Harry Potter": [r"harry potter", r"wizarding world", r"fantastic beasts"],
    "Lord of the Rings": [r"lord of the rings", r"\blotr\b", r"the hobbit"],
    "James Bond": [r"james bond", r"007"],
}

GENRE_KEYWORDS = {
    "Sci-Fi Classics": [r"sci-fi", r"science fiction", r"space", r"alien", r"cyberpunk"],
    "Oscar Winners": [r"oscar", r"academy award", r"best picture"],
    "90s Action": [r"action"],
}


def create_groupings(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    if not items:
        return {}

    groupings: Dict[str, List[Dict[str, Any]]] = {}

    for item in items:
        title = item.get("Name", "")
        overview = item.get("Overview", "")
        text_to_check = f"{title} {overview}".lower()

        for franchise_name, patterns in FRANCHISE_RULES.items():
            for pattern in patterns:
                if re.search(pattern, text_to_check, re.IGNORECASE):
                    groupings.setdefault(franchise_name, []).append(item)
                    break

        for genre_name, patterns in GENRE_KEYWORDS.items():
            for pattern in patterns:
                if re.search(pattern, text_to_check, re.IGNORECASE):
                    groupings.setdefault(genre_name, []).append(item)
                    break

    decade_groups = group_by_decade(items)
    for dec, dec_items in decade_groups.items():
        if dec_items:
            groupings.setdefault(dec, []).extend(dec_items)

    return groupings


def group_by_tag(items: List[Dict[str, Any]], min_items: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    tag_groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        tags = item.get("Tags") or []
        for tag in tags:
            tag_groups.setdefault(tag, []).append(item)
    return {k: v for k, v in tag_groups.items() if len(v) >= min_items}


def group_by_genre(items: List[Dict[str, Any]], min_items: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    genre_groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        genres = item.get("Genres") or []
        for genre in genres:
            genre_groups.setdefault(genre, []).append(item)
    return {k: v for k, v in genre_groups.items() if len(v) >= min_items}


def group_by_studio(items: List[Dict[str, Any]], min_items: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    studio_groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        studios = item.get("Studios") or []
        for studio in studios:
            s_name = studio.get("Name") if isinstance(studio, dict) else str(studio)
            if s_name:
                studio_groups.setdefault(s_name, []).append(item)
    return {k: v for k, v in studio_groups.items() if len(v) >= min_items}


def group_by_director(items: List[Dict[str, Any]], min_items: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    director_groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        people = item.get("People") or []
        directors = []
        if isinstance(people, list):
            for person in people:
                if isinstance(person, dict) and person.get("Type") == "Director":
                    d_name = person.get("Name")
                    if d_name:
                        directors.append(d_name)
        elif item.get("Director"):
            directors.append(str(item.get("Director")))
        
        for director in directors:
            director_groups.setdefault(director, []).append(item)
            
    return {k: v for k, v in director_groups.items() if len(v) >= min_items}


def group_by_decade(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    collections: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        year = None
        prod_year = item.get("ProductionYear")
        if isinstance(prod_year, int) and prod_year > 0:
            year = prod_year
        elif isinstance(prod_year, str) and prod_year.isdigit():
            year = int(prod_year)
        
        if year is None and item.get("PremiereDate"):
            pdate = item.get("PremiereDate")
            if isinstance(pdate, str) and len(pdate) >= 4 and pdate[:4].isdigit():
                year = int(pdate[:4])
            elif isinstance(pdate, (int, float)):
                year = int(pdate)
        
        if year and 1800 <= year <= 2100:
            decade = f"{(year // 10) * 10}s Movies"
            if decade not in collections:
                collections[decade] = []
            collections[decade].append(item)

    return collections
