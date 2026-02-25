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
        {"Name": "TV Shows", "ItemId": "tvshows_id", "CollectionType": "tvshows"}
    ],
    "users": [
        {"Name": "Admin", "Id": "admin_id"}
    ],
    "items": [
        {
            "Id": "1",
            "Name": "Inception",
            "Type": "Movie",
            "ProviderIds": {"Imdb": "tt1375666"},
            "ProductionYear": 2010,
            "Genres": ["Action", "Sci-Fi"]
        },
        {
            "Id": "2",
            "Name": "The Matrix",
            "Type": "Movie",
            "ProviderIds": {"Imdb": "tt0133093"},
            "ProductionYear": 1999,
            "Genres": ["Action", "Sci-Fi"]
        }
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
                {''.join(f"<tr><td>{i.get('Name')}</td><td>{i.get('Id')}</td><td>{i.get('Type')}</td><td>{i.get('ProductionYear')}</td><td>{i.get('ProviderIds', {{}}).get('Imdb', '')}</td></tr>" for i in data['items'])}
            </table>
        </div>
    </body>
    </html>
    """
    return html

if __name__ == '__main__':
    app.run(port=8096, debug=True)
