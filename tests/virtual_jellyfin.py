import flask
from flask import Flask, request, jsonify, send_file
import uuid
import os
import io

app = Flask(__name__)

# In-memory storage
data = {
    "libraries": [
        {"Name": "Movies", "ItemId": "movies_id", "CollectionType": "movies"},
        {"Name": "TV Shows", "ItemId": "tvshows_id", "CollectionType": "tvshows"},
        {"Name": "Anime", "ItemId": "anime_id", "CollectionType": "tvshows"},
        {"Name": "Documentaries", "ItemId": "docs_id", "CollectionType": "movies"}
    ],
    "users": [
        {"Name": "Admin", "Id": "admin_id"},
        {"Name": "User1", "Id": "user1_id"},
        {"Name": "Guest", "Id": "guest_id"}
    ],
    "items": [
        # --- Movies (1-50) ---
        {"Id": "m1", "Name": "Inception", "Type": "Movie", "ProviderIds": {"Imdb": "tt1375666"}, "ProductionYear": 2010, "Genres": ["Action", "Sci-Fi"], "Path": "/media/movies/Inception (2010)/Inception.mkv"},
        {"Id": "m2", "Name": "The Matrix", "Type": "Movie", "ProviderIds": {"Imdb": "tt0133093"}, "ProductionYear": 1999, "Genres": ["Action", "Sci-Fi"], "Path": "/media/movies/The Matrix (1999)/The Matrix.mkv"},
        {"Id": "m3", "Name": "Interstellar", "Type": "Movie", "ProviderIds": {"Imdb": "tt0816692"}, "ProductionYear": 2014, "Genres": ["Adventure", "Drama", "Sci-Fi"], "Path": "/media/movies/Interstellar (2014)/Interstellar.mkv"},
        {"Id": "m4", "Name": "The Godfather", "Type": "Movie", "ProviderIds": {"Imdb": "tt0068646"}, "ProductionYear": 1972, "Genres": ["Crime", "Drama"], "Path": "/media/movies/The Godfather (1972)/The Godfather.mkv"},
        {"Id": "m5", "Name": "Pulp Fiction", "Type": "Movie", "ProviderIds": {"Imdb": "tt0110912"}, "ProductionYear": 1994, "Genres": ["Crime", "Drama"], "Path": "/media/movies/Pulp Fiction (1994)/Pulp Fiction.mkv"},
        {"Id": "m6", "Name": "The Dark Knight", "Type": "Movie", "ProviderIds": {"Imdb": "tt0468569"}, "ProductionYear": 2008, "Genres": ["Action", "Crime", "Drama"], "Path": "/media/movies/The Dark Knight (2008)/The Dark Knight.mkv"},
        {"Id": "m7", "Name": "Schindler's List", "Type": "Movie", "ProviderIds": {"Imdb": "tt0108052"}, "ProductionYear": 1993, "Genres": ["Biography", "Drama", "History"], "Path": "/media/movies/Schindler's List (1993)/Schindler's List.mkv"},
        {"Id": "m8", "Name": "The Shawshank Redemption", "Type": "Movie", "ProviderIds": {"Imdb": "tt0111161"}, "ProductionYear": 1994, "Genres": ["Drama"], "Path": "/media/movies/The Shawshank Redemption (1994)/The Shawshank Redemption.mkv"},
        {"Id": "m9", "Name": "Fight Club", "Type": "Movie", "ProviderIds": {"Imdb": "tt0137523"}, "ProductionYear": 1999, "Genres": ["Drama"], "Path": "/media/movies/Fight Club (1999)/Fight Club.mkv"},
        {"Id": "m10", "Name": "Forrest Gump", "Type": "Movie", "ProviderIds": {"Imdb": "tt0109830"}, "ProductionYear": 1994, "Genres": ["Drama", "Romance"], "Path": "/media/movies/Forrest Gump (1994)/Forrest Gump.mkv"},
        {"Id": "m21", "Name": "Parasite", "Type": "Movie", "ProviderIds": {"Imdb": "tt6751668"}, "ProductionYear": 2019, "Genres": ["Drama", "Thriller"], "Path": "/media/movies/Parasite (2019)/Parasite.mkv"},
        {"Id": "m22", "Name": "Spirited Away", "Type": "Movie", "ProviderIds": {"Imdb": "tt0245429"}, "ProductionYear": 2001, "Genres": ["Animation", "Adventure", "Family"], "Path": "/media/movies/Spirited Away (2001)/Spirited Away.mkv"},
        {"Id": "m23", "Name": "The Lion King", "Type": "Movie", "ProviderIds": {"Imdb": "tt0110357"}, "ProductionYear": 1994, "Genres": ["Animation", "Adventure", "Drama"], "Path": "/media/movies/The Lion King (1994)/The Lion King.mkv"},
        {"Id": "m24", "Name": "Gladiator", "Type": "Movie", "ProviderIds": {"Imdb": "tt0172495"}, "ProductionYear": 2000, "Genres": ["Action", "Adventure", "Drama"], "Path": "/media/movies/Gladiator (2000)/Gladiator.mkv"},
        {"Id": "m25", "Name": "The Silence of the Lambs", "Type": "Movie", "ProviderIds": {"Imdb": "tt0102926"}, "ProductionYear": 1991, "Genres": ["Crime", "Drama", "Thriller"], "Path": "/media/movies/The Silence of the Lambs (1991)/The Silence of the Lambs.mkv"},
        {"Id": "m26", "Name": "Saving Private Ryan", "Type": "Movie", "ProviderIds": {"Imdb": "tt0120815"}, "ProductionYear": 1998, "Genres": ["Drama", "War"], "Path": "/media/movies/Saving Private Ryan (1998)/Saving Private Ryan.mkv"},
        {"Id": "m27", "Name": "The Green Mile", "Type": "Movie", "ProviderIds": {"Imdb": "tt0120689"}, "ProductionYear": 1999, "Genres": ["Crime", "Drama", "Fantasy"], "Path": "/media/movies/The Green Mile (1999)/The Green Mile.mkv"},
        {"Id": "m28", "Name": "Life Is Beautiful", "Type": "Movie", "ProviderIds": {"Imdb": "tt0118799"}, "ProductionYear": 1997, "Genres": ["Comedy", "Drama", "Romance"], "Path": "/media/movies/Life Is Beautiful (1997)/Life Is Beautiful.mkv"},
        {"Id": "m29", "Name": "Se7en", "Type": "Movie", "ProviderIds": {"Imdb": "tt0114369"}, "ProductionYear": 1995, "Genres": ["Crime", "Drama", "Mystery"], "Path": "/media/movies/Se7en (1995)/Se7en.mkv"},
        {"Id": "m30", "Name": "Leon: The Professional", "Type": "Movie", "ProviderIds": {"Imdb": "tt0110413"}, "ProductionYear": 1994, "Genres": ["Action", "Crime", "Drama"], "Path": "/media/movies/Leon (1994)/Leon.mkv"},
        {"Id": "m31", "Name": "Star Wars: Episode IV - A New Hope", "Type": "Movie", "ProviderIds": {"Imdb": "tt0076759"}, "ProductionYear": 1977, "Genres": ["Action", "Adventure", "Fantasy"], "Path": "/media/movies/Star Wars (1977)/Star Wars.mkv"},
        {"Id": "m32", "Name": "The Lord of the Rings: The Fellowship of the Ring", "Type": "Movie", "ProviderIds": {"Imdb": "tt0120737"}, "ProductionYear": 2001, "Genres": ["Action", "Adventure", "Drama"], "Path": "/media/movies/LOTR 1 (2001)/LOTR 1.mkv"},
        {"Id": "m33", "Name": "The Lord of the Rings: The Two Towers", "Type": "Movie", "ProviderIds": {"Imdb": "tt0167261"}, "ProductionYear": 2002, "Genres": ["Action", "Adventure", "Drama"], "Path": "/media/movies/LOTR 2 (2002)/LOTR 2.mkv"},
        {"Id": "m34", "Name": "The Lord of the Rings: The Return of the King", "Type": "Movie", "ProviderIds": {"Imdb": "tt0167260"}, "ProductionYear": 2003, "Genres": ["Action", "Adventure", "Drama"], "Path": "/media/movies/LOTR 3 (2003)/LOTR 3.mkv"},
        {"Id": "m35", "Name": "The Matrix Reloaded", "Type": "Movie", "ProviderIds": {"Imdb": "tt0234215"}, "ProductionYear": 2003, "Genres": ["Action", "Sci-Fi"], "Path": "/media/movies/The Matrix Reloaded (2003)/Matrix Reloaded.mkv"},
        {"Id": "m36", "Name": "The Matrix Revolutions", "Type": "Movie", "ProviderIds": {"Imdb": "tt0242653"}, "ProductionYear": 2003, "Genres": ["Action", "Sci-Fi"], "Path": "/media/movies/The Matrix Revolutions (2003)/Matrix Revolutions.mkv"},
        {"Id": "m37", "Name": "Django Unchained", "Type": "Movie", "ProviderIds": {"Imdb": "tt1853728"}, "ProductionYear": 2012, "Genres": ["Drama", "Western"], "Path": "/media/movies/Django Unchained (2012)/Django.mkv"},
        {"Id": "m38", "Name": "The Departed", "Type": "Movie", "ProviderIds": {"Imdb": "tt0407887"}, "ProductionYear": 2006, "Genres": ["Crime", "Drama", "Thriller"], "Path": "/media/movies/The Departed (2006)/The Departed.mkv"},
        {"Id": "m39", "Name": "The Prestige", "Type": "Movie", "ProviderIds": {"Imdb": "tt0482571"}, "ProductionYear": 2006, "Genres": ["Drama", "Mystery", "Sci-Fi"], "Path": "/media/movies/The Prestige (2006)/The Prestige.mkv"},
        {"Id": "m40", "Name": "The Lion King", "Type": "Movie", "ProviderIds": {"Imdb": "tt0110357"}, "ProductionYear": 1994, "Genres": ["Animation", "Adventure", "Drama"], "Path": "/media/movies/The Lion King (1994)/Lion King.mkv"},
        {"Id": "m41", "Name": "Back to the Future", "Type": "Movie", "ProviderIds": {"Imdb": "tt0088763"}, "ProductionYear": 1985, "Genres": ["Adventure", "Comedy", "Sci-Fi"], "Path": "/media/movies/Back to the Future (1985)/BTTF 1.mkv"},
        {"Id": "m42", "Name": "Back to the Future Part II", "Type": "Movie", "ProviderIds": {"Imdb": "tt0096895"}, "ProductionYear": 1989, "Genres": ["Adventure", "Comedy", "Sci-Fi"], "Path": "/media/movies/Back to the Future II (1989)/BTTF 2.mkv"},
        {"Id": "m43", "Name": "Back to the Future Part III", "Type": "Movie", "ProviderIds": {"Imdb": "tt0099088"}, "ProductionYear": 1990, "Genres": ["Adventure", "Comedy", "Sci-Fi"], "Path": "/media/movies/Back to the Future III (1990)/BTTF 3.mkv"},
        {"Id": "m44", "Name": "The Shining", "Type": "Movie", "ProviderIds": {"Imdb": "tt0081505"}, "ProductionYear": 1980, "Genres": ["Drama", "Horror"], "Path": "/media/movies/The Shining (1980)/The Shining.mkv"},
        {"Id": "m45", "Name": "Alien", "Type": "Movie", "ProviderIds": {"Imdb": "tt0078748"}, "ProductionYear": 1979, "Genres": ["Horror", "Sci-Fi"], "Path": "/media/movies/Alien (1979)/Alien.mkv"},
        {"Id": "m46", "Name": "Aliens", "Type": "Movie", "ProviderIds": {"Imdb": "tt0090605"}, "ProductionYear": 1986, "Genres": ["Action", "Adventure", "Sci-Fi"], "Path": "/media/movies/Aliens (1986)/Aliens.mkv"},
        {"Id": "m47", "Name": "Psycho", "Type": "Movie", "ProviderIds": {"Imdb": "tt0054215"}, "ProductionYear": 1960, "Genres": ["Horror", "Mystery", "Thriller"], "Path": "/media/movies/Psycho (1960)/Psycho.mkv"},
        {"Id": "m48", "Name": "The Intouchables", "Type": "Movie", "ProviderIds": {"Imdb": "tt1675434"}, "ProductionYear": 2011, "Genres": ["Biography", "Comedy", "Drama"], "Path": "/media/movies/The Intouchables (2011)/Intouchables.mkv"},
        {"Id": "m49", "Name": "City of God", "Type": "Movie", "ProviderIds": {"Imdb": "tt0317248"}, "ProductionYear": 2002, "Genres": ["Crime", "Drama"], "Path": "/media/movies/City of God (2002)/City of God.mkv"},
        {"Id": "m50", "Name": "Spiderman: Into the Spiderverse", "Type": "Movie", "ProviderIds": {"Imdb": "tt4633694"}, "ProductionYear": 2018, "Genres": ["Animation", "Action", "Adventure"], "Path": "/media/movies/Spiderverse (2018)/Spiderverse.mkv"},

        # --- Series (51-80) ---
        {"Id": "s1", "Name": "Breaking Bad", "Type": "Series", "ProviderIds": {"Imdb": "tt0903747"}, "ProductionYear": 2008, "Genres": ["Crime", "Drama", "Thriller"], "Path": "/media/tv/Breaking Bad/Season 1/S01E01.mkv"},
        {"Id": "s1_e1", "Name": "Pilot", "Type": "Episode", "SeriesId": "s1", "SeriesName": "Breaking Bad", "SeasonId": "s1_s1", "SeasonName": "Season 1", "IndexNumber": 1, "Path": "/media/tv/Breaking Bad/Season 1/S01E01.mkv"},
        {"Id": "s2", "Name": "The Sopranos", "Type": "Series", "ProviderIds": {"Imdb": "tt0141842"}, "ProductionYear": 1999, "Genres": ["Crime", "Drama"], "Path": "/media/tv/The Sopranos/Season 1/S01E01.mkv"},
        {"Id": "s3", "Name": "Stranger Things", "Type": "Series", "ProviderIds": {"Imdb": "tt4574334"}, "ProductionYear": 2016, "Genres": ["Drama", "Fantasy", "Horror"], "Path": "/media/tv/Stranger Things/Season 1/S01E01.mkv"},
        {"Id": "s4", "Name": "The Office", "Type": "Series", "ProviderIds": {"Imdb": "tt0386676"}, "ProductionYear": 2005, "Genres": ["Comedy"], "Path": "/media/tv/The Office/Season 1/S01E01.mkv"},
        {"Id": "s5", "Name": "Game of Thrones", "Type": "Series", "ProviderIds": {"Imdb": "tt0944947"}, "ProductionYear": 2011, "Genres": ["Action", "Adventure", "Drama"], "Path": "/media/tv/Game of Thrones/Season 1/S01E01.mkv"},
        {"Id": "s6", "Name": "The Wire", "Type": "Series", "ProviderIds": {"Imdb": "tt0306414"}, "ProductionYear": 2002, "Genres": ["Crime", "Drama", "Thriller"], "Path": "/media/tv/The Wire/Season 1/S01E01.mkv"},
        {"Id": "s7", "Name": "Friends", "Type": "Series", "ProviderIds": {"Imdb": "tt0108778"}, "ProductionYear": 1994, "Genres": ["Comedy", "Romance"], "Path": "/media/tv/Friends/Season 1/S01E01.mkv"},
        {"Id": "s8", "Name": "Sherlock", "Type": "Series", "ProviderIds": {"Imdb": "tt1475582"}, "ProductionYear": 2010, "Genres": ["Crime", "Drama", "Mystery"], "Path": "/media/tv/Sherlock/Season 1/S01E01.mkv"},
        {"Id": "s9", "Name": "Better Call Saul", "Type": "Series", "ProviderIds": {"Imdb": "tt3032476"}, "ProductionYear": 2015, "Genres": ["Crime", "Drama"], "Path": "/media/tv/Better Call Saul/Season 1/S01E01.mkv"},
        {"Id": "s10", "Name": "Chernobyl", "Type": "Series", "ProviderIds": {"Imdb": "tt8162467"}, "ProductionYear": 2019, "Genres": ["Drama", "History", "Thriller"], "Path": "/media/tv/Chernobyl/Season 1/S01E01.mkv"},
        {"Id": "s11", "Name": "The Mandalorian", "Type": "Series", "ProviderIds": {"Imdb": "tt8111088"}, "ProductionYear": 2019, "Genres": ["Action", "Adventure", "Sci-Fi"], "Path": "/media/tv/The Mandalorian/Season 1/S01E01.mkv"},
        {"Id": "s12", "Name": "Black Mirror", "Type": "Series", "ProviderIds": {"Imdb": "tt2085059"}, "ProductionYear": 2011, "Genres": ["Drama", "Sci-Fi", "Thriller"], "Path": "/media/tv/Black Mirror/Season 1/S01E01.mkv"},
        {"Id": "s13", "Name": "True Detective", "Type": "Series", "ProviderIds": {"Imdb": "tt2356777"}, "ProductionYear": 2014, "Genres": ["Crime", "Drama", "Mystery"], "Path": "/media/tv/True Detective/Season 1/S01E01.mkv"},
        {"Id": "s14", "Name": "The Boys", "Type": "Series", "ProviderIds": {"Imdb": "tt1190634"}, "ProductionYear": 2019, "Genres": ["Action", "Comedy", "Crime"], "Path": "/media/tv/The Boys/Season 1/S01E01.mkv"},
        {"Id": "s15", "Name": "Fargo", "Type": "Series", "ProviderIds": {"Imdb": "tt2802142"}, "ProductionYear": 2014, "Genres": ["Crime", "Drama", "Thriller"], "Path": "/media/tv/Fargo/Season 1/S01E01.mkv"},

        # --- Documentary/Anime (81-100) ---
        {"Id": "d1", "Name": "Planet Earth", "Type": "Series", "ProviderIds": {"Imdb": "tt0795176"}, "ProductionYear": 2006, "Genres": ["Documentary"], "Path": "/media/docs/Planet Earth/Season 1/S01E01.mkv"},
        {"Id": "d2", "Name": "Our Planet", "Type": "Series", "ProviderIds": {"Imdb": "tt9253866"}, "ProductionYear": 2019, "Genres": ["Documentary"], "Path": "/media/docs/Our Planet/Season 1/S01E01.mkv"},
        {"Id": "d3", "Name": "Cosmos: A Spacetime Odyssey", "Type": "Series", "ProviderIds": {"Imdb": "tt2395695"}, "ProductionYear": 2014, "Genres": ["Documentary"], "Path": "/media/docs/Cosmos/Season 1/S01E01.mkv"},
        {"Id": "a1", "Name": "Fullmetal Alchemist: Brotherhood", "Type": "Series", "ProviderIds": {"Imdb": "tt1405365"}, "ProductionYear": 2009, "Genres": ["Animation", "Action", "Adventure"], "Path": "/media/anime/FMA Brotherhood/Season 1/S01E01.mkv"},
        {"Id": "a2", "Name": "Attack on Titan", "Type": "Series", "ProviderIds": {"Imdb": "tt2560140"}, "ProductionYear": 2013, "Genres": ["Animation", "Action", "Adventure"], "Path": "/media/anime/Attack on Titan/Season 1/S01E01.mkv"},
        {"Id": "a3", "Name": "Death Note", "Type": "Series", "ProviderIds": {"Imdb": "tt0877057"}, "ProductionYear": 2006, "Genres": ["Animation", "Crime", "Drama"], "Path": "/media/anime/Death Note/Season 1/S01E01.mkv"},
        {"Id": "a4", "Name": "Cowboy Bebop", "Type": "Series", "ProviderIds": {"Imdb": "tt0213338"}, "ProductionYear": 1998, "Genres": ["Animation", "Action", "Adventure"], "Path": "/media/anime/Cowboy Bebop/Season 1/S01E01.mkv"},
        {"Id": "a5", "Name": "One Punch Man", "Type": "Series", "ProviderIds": {"Imdb": "tt4508902"}, "ProductionYear": 2015, "Genres": ["Animation", "Action", "Comedy"], "Path": "/media/anime/One Punch Man/Season 1/S01E01.mkv"},
        {"Id": "a6", "Name": "Hunter x Hunter", "Type": "Series", "ProviderIds": {"Imdb": "tt2064540"}, "ProductionYear": 2011, "Genres": ["Animation", "Action", "Adventure"], "Path": "/media/anime/Hunter x Hunter/Season 1/S01E01.mkv"},
        {"Id": "a7", "Name": "Steins;Gate", "Type": "Series", "ProviderIds": {"Imdb": "tt1910272"}, "ProductionYear": 2011, "Genres": ["Animation", "Drama", "Sci-Fi"], "Path": "/media/anime/Steins Gate/Season 1/S01E01.mkv"},

        # --- Fillers (101-120) ---
        *[{"Id": f"gen_m{i}", "Name": f"Generic Movie {i}", "Type": "Movie", "ProductionYear": 2000 + (i % 25), "Genres": ["Drama"], "Path": f"/media/movies/Generic {i}.mkv"} for i in range(101, 121)],
        *[{"Id": f"gen_s{i}", "Name": f"Generic Series {i}", "Type": "Series", "ProductionYear": 2010 + (i % 15), "Genres": ["Comedy"], "Path": f"/media/tv/Generic {i}/S01E01.mkv"} for i in range(121, 141)],

        # --- DIGITAL CHAOS ---
        {"Id": "chaos_1", "Name": "Duplicate ID Test A", "Type": "Movie", "ProductionYear": 2020, "Path": "/media/movies/chaos1a.mkv"},
        {"Id": "chaos_1", "Name": "Duplicate ID Test B", "Type": "Movie", "ProductionYear": 2021, "Path": "/media/movies/chaos1b.mkv"},
        {"Id": "chaos_2", "Name": "Malformed Year", "Type": "Movie", "ProductionYear": "Nineteen Ninety Nine", "Path": "/media/movies/chaos2.mkv"},
        {"Id": "chaos_3", "Name": "Emoji Title 🎬🔥", "Type": "Movie", "ProductionYear": 2023, "Path": "/media/movies/chaos3.mkv"},
        {"Id": "chaos_4", "Name": "RTL Title (Hebrew) שלום", "Type": "Movie", "ProductionYear": 2022, "Path": "/media/movies/chaos4.mkv"},
        {"Id": "chaos_5", "Name": "NULL Path Item", "Type": "Movie", "ProductionYear": 2021, "Path": None},
        {"Id": "chaos_6", "Name": "Invalid Item Type", "Type": "Folder", "ProductionYear": 2020, "Path": "/media/folder"},
        {"Id": "chaos_7", "Name": "Mixed Case ID", "Id": "ChAoS_7", "Type": "Movie", "ProductionYear": 2020, "Path": "/media/chaos7.mkv"},
        {"Id": "chaos_8", "Name": "RTL and LTR Mixed: Hello שלום World", "Type": "Movie", "ProductionYear": 2023, "Path": "/media/movies/chaos8.mkv"}
    ],
    "library_paths": {},
    "images": {}
}

@app.route('/Items', methods=['GET'])
def get_items():
    api_key = request.args.get('api_key') or request.headers.get('X-Emby-Token')
    
    # MAGIC: 401 Unauthorized
    if not api_key or api_key == "BAD_KEY":
        return "Unauthorized", 401
        
    # MAGIC: Timeout
    if api_key == "TIMEOUT_KEY":
        import time
        time.sleep(3)
        return "Timeout test", 200
        
    # MAGIC: Rate Limit Simulation
    if api_key == "RATE_LIMIT_KEY":
        import time
        time.sleep(5) # Very slow
        return jsonify({"Items": data["items"]})

    # MAGIC: Large Response
    if api_key == "LARGE_RESPONSE_KEY":
        large_items = data["items"] * 40 # Total ~1200 items
        return jsonify({"Items": large_items, "TotalRecordCount": len(large_items)})

    # MAGIC: Empty Items
    if api_key == "EMPTY_ITEMS_KEY":
        return jsonify({"Items": []})
        
    # MAGIC: Missing Items List
    if api_key == "MISSING_ITEMS_KEY":
        return jsonify({"NotItems": "Missing"})
        
    # MAGIC: Malformed JSON
    if api_key == "MALFORMED_JSON_KEY":
        return "Not JSON at all", 200

    return jsonify({"Items": data["items"]})

@app.route('/System/Info', methods=['GET'])
def get_system_info():
    return jsonify({
        "LocalAddress": "http://127.0.0.1:8096",
        "ServerName": "Virtual-Jellyfin-Mock",
        "Version": "10.8.10",
        "Id": "mock-server-id"
    })

@app.route('/Library/VirtualFolders', methods=['GET'])
def get_virtual_folders():
    api_key = request.args.get('api_key') or request.headers.get('X-Emby-Token')
    
    if api_key == "LIB_GET_500":
        return "Internal Error", 500
    if api_key == "LIB_GET_MISSING_NAME":
        return jsonify([{"ItemId": "id1", "CollectionType": "movies"}])
    if api_key == "LIB_GET_EMPTY":
        return jsonify([])
    if api_key == "LIB_GET_MISSING_ID":
        return jsonify([{"Name": "Movies"}])
        
    return jsonify(data["libraries"])

@app.route('/Library/VirtualFolders', methods=['POST'])
def add_virtual_folder():
    name = request.args.get('name')
    collection_type = request.args.get('collectionType', 'movies')
    
    # MAGIC: 500 Server Error on Create
    if name == "FAIL_CREATE":
        return "Create Failed", 500
    
    for lib in data["libraries"]:
        if lib["Name"] == name:
            return "Conflict", 409
            
    new_lib = {
        "Name": name,
        "ItemId": str(uuid.uuid4()),
        "CollectionType": collection_type
    }
    data["libraries"].append(new_lib)
    return "", 204

@app.route('/Library/VirtualFolders', methods=['DELETE'])
def delete_virtual_folder():
    name = request.args.get('name')
    
    # MAGIC: DELETE 404
    if name == "FAIL_DELETE_404":
        return "Not Found", 404
    # MAGIC: DELETE 500
    if name == "FAIL_DELETE_500":
        return "Server Error", 500
        
    data["libraries"] = [lib for lib in data["libraries"] if lib["Name"] != name]
    return "", 204

@app.route('/Library/VirtualFolders/Paths', methods=['POST'])
def add_library_path():
    req_data = request.json
    name = req_data.get('Name')
    path = req_data.get('Path')
    
    # MAGIC: 400 Bad Request on Paths
    if "FAIL_PATH" in path:
        return "Bad Path", 400
        
    if name not in data["library_paths"]:
        data["library_paths"][name] = []
    data["library_paths"][name].append(path)
    return "", 204

@app.route('/Library/Refresh', methods=['POST'])
def refresh_library():
    api_key = request.headers.get('X-Emby-Token')
    
    # We use a global trigger since Refresh doesn't receive the name. 
    # Let's say we trigger this via a specific API key for simplicity.
    if api_key == "FAIL_REFRESH_KEY":
        return "Bad Gateway", 502
        
    return "", 204

@app.route('/Users', methods=['GET'])
def get_users():
    api_key = request.headers.get('X-Emby-Token')
    if api_key == "USER_GET_500":
        return "Internal Error", 500
    if api_key == "BAD_KEY":
        return "Unauthorized", 401
    return jsonify(data["users"])

@app.route('/Users/<user_id>/Items', methods=['GET'])
def get_user_items(user_id):
    if user_id == "BAD_USER":
        return jsonify({"Items": []})
    if user_id == "MISSING_DATA_USER":
        return jsonify({}) # Missing Items key
    return jsonify({"Items": data["items"]})

@app.route('/Items/<item_id>/Images/Primary', methods=['POST'])
def set_item_image(item_id):
    if item_id == "FAIL_IMAGE_ID":
        return "Bad Image Data", 400
    data["images"][item_id] = request.data
    return "", 204

@app.route('/', methods=['GET'])
def dashboard():
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Virtual Jellyfin Dashboard</title>
        <style>
            body {{ font-family: sans-serif; margin: 2rem; background: #1a1b1e; color: #e4e5e8; }}
            h1, h2 {{ color: #00a4dc; }}
            .card {{ background: #2b2d31; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #4f545c; }}
            th {{ background: #1e1f22; }}
        </style>
    </head>
    <body>
        <h1>Virtual Jellyfin State</h1>
        
        <div class="card">
            <h2>Libraries</h2>
            <table>
                <tr><th>Name</th><th>ItemId</th><th>CollectionType</th><th>Paths</th></tr>
                {''.join(f"<tr><td>{lib.get('Name')}</td><td>{lib.get('ItemId')}</td><td>{lib.get('CollectionType')}</td><td>{data['library_paths'].get(lib.get('Name'), [])}</td></tr>" for lib in data['libraries'])}
            </table>
        </div>

        <div class="card">
            <h2>Users</h2>
            <table>
                <tr><th>Name</th><th>Id</th></tr>
                {''.join(f"<tr><td>{u.get('Name')}</td><td>{u.get('Id')}</td></tr>" for u in data['users'])}
            </table>
        </div>

        <div class="card">
            <h2>Items</h2>
            <table>
                <tr><th>Name</th><th>Id</th><th>Type</th><th>Year</th><th>Imdb</th></tr>
                {''.join(f"<tr><td>{i.get('Name')}</td><td>{i.get('Id')}</td><td>{i.get('Type')}</td><td>{i.get('ProductionYear')}</td><td>{i.get('ProviderIds', {}).get('Imdb', '')}</td></tr>" for i in data['items'])}
            </table>
        </div>
    </body>
    </html>
    """
    return html

if __name__ == '__main__':
    app.run(port=8096, debug=True)
