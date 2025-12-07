import json
import os
from flask import Flask, render_template, send_file
import config

# Create the Flask application instance.
# 'template_folder' tells Flask where to look for HTML files.
# 'static_folder' tells Flask where to look for CSS/JS files.
app = Flask(__name__, template_folder='templates', static_folder='static')

@app.route('/')
def index():
    """
    Main Route (Root URL)
    ---------------------
    This function processes requests to the home page ('/').
    It reads the metrics JSON file and renders the HTML template.
    """
    
    # 1. Load the detections from the JSON file specified in config.py
    #    The structure is expected to be: { "predictions": [ { "pred_bbox": [x1, y1, x2, y2], ... }, ... ] }
    detections_path = config.METRICS_PATH
    if not os.path.exists(detections_path):
        return f"Error: File not found at {detections_path}", 404

    with open(detections_path, 'r') as f:
        data = json.load(f)

    # 2. Extract predictions. 
    #    We pass this list to the HTML template so Javascript can use it.
    predictions = data.get('predictions', [])

    # 3. Render the 'index.html' template.
    #    We pass the 'predictions' list as a variable named 'barlines'.
    #    We also pass the image source URL (see the /image route below).
    return render_template('index.html', barlines=predictions, image_url='/image')


@app.route('/image')
def serve_image():
    """
    Image Route
    -----------
    This function serves the page image file.
    It reads the file from config.IMAGE_PATH and sends it to the browser.
    This allows us to load images from anywhere on the disk without moving them to 'static/'.
    """
    image_path = config.IMAGE_PATH
    if not os.path.exists(image_path):
        return "Error: Image not found", 404
        
    return send_file(image_path, mimetype='image/png')


@app.route('/save_decisions', methods=['POST'])
def save_decisions():
    """
    Save Decisions Route
    --------------------
    Method: POST
    Expects: JSON body with {"ignored_ids": [int, int, ...]}
    
    This function is called when the user clicks 'Save ignored barlines' in the browser.
    It writes the list of ignored IDs to the MANUAL_IGNORE_PATH defined in config.
    """
    from flask import request
    
    # 1. Parse the JSON data from the request body
    data = request.get_json()
    if not data or 'ignored_ids' not in data:
        return {"status": "error", "message": "Missing ignored_ids"}, 400
        
    ignored_ids = data['ignored_ids']
    
    # 2. Basic validation: ensure it's a list
    if not isinstance(ignored_ids, list):
        return {"status": "error", "message": "ignored_ids must be a list"}, 400

    # 3. Create the output dictionary with a timestamp
    import datetime
    output_data = {
        "ignored_ids": ignored_ids,
        "updated_at": datetime.datetime.now().isoformat()
    }
    
    # 4. Write to the file
    target_file = config.MANUAL_IGNORE_PATH
    try:
        with open(target_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        print(f"Successfully saved {len(ignored_ids)} ignored IDs to {target_file}")
        return {"status": "ok", "count": len(ignored_ids), "path": target_file}
        
    except Exception as e:
        print(f"Error saving file: {e}")
        return {"status": "error", "message": str(e)}, 500


if __name__ == '__main__':
    # usage: python tools/gui_helper/app.py
    # This runs the development server on localhost:5000
    print(f"Starting GUI Helper...")
    print(f"Loading data from: {config.METRICS_PATH}")
    app.run(debug=True, port=5000)
