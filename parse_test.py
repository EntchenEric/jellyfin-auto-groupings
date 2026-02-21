import re

def parse_complex_query(query, default_type):
    pattern = re.compile(r'\s+(AND NOT|OR NOT|AND|OR)\s+', re.IGNORECASE)
    parts = pattern.split(query.strip())
    
    rules = []
    
    rules.append({
        "operator": "AND",
        "type": default_type,
        "value": parts[0].strip()
    })
    
    for i in range(1, len(parts), 2):
        op = parts[i].upper().replace('  ', ' ')
        val = parts[i+1].strip()
        rules.append({
            "operator": op,
            "type": default_type,
            "value": val
        })
        
    return rules

print(parse_complex_query("Horror AND animation AND NOT comedy", "genre"))
