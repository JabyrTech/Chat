from flask import request, jsonify, current_app
from werkzeug.utils import secure_filename
import os
import uuid
from PIL import Image
import mimetypes

ALLOWED_EXTENSIONS = {
    'image': {'png', 'jpg', 'jpeg', 'gif', 'webp'},
    'file': {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'zip', 'rar'},
    'voice': {'wav', 'mp3', 'ogg', 'webm', 'm4a'}
}

def allowed_file(filename, file_type):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS.get(file_type, set())

def get_file_type(filename):
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    for file_type, extensions in ALLOWED_EXTENSIONS.items():
        if extension in extensions:
            return file_type
    return 'file'

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    file_type = request.form.get('type', 'file')
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename, file_type):
        # Generate unique filename
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        
        # Determine upload path based on file type
        if file_type == 'image':
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'images')
        elif file_type == 'voice':
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'voice')
        else:
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'files')
        
        os.makedirs(upload_path, exist_ok=True)
        file_path = os.path.join(upload_path, unique_filename)
        file.save(file_path)
        
        # Process image files
        if file_type == 'image':
            try:
                # Create thumbnail
                with Image.open(file_path) as img:
                    img.thumbnail((800, 600), Image.Resampling.LANCZOS)
                    img.save(file_path, optimize=True, quality=85)
            except Exception as e:
                print(f"Error processing image: {e}")
        
        # Get file size
        file_size = os.path.getsize(file_path)
        file_size_str = format_file_size(file_size)
        
        # Generate file URL
        file_url = f"/static/uploads/{file_type}s/{unique_filename}" if file_type in ['image', 'voice'] else f"/static/uploads/files/{unique_filename}"
        
        return jsonify({
            'success': True,
            'file_url': file_url,
            'file_name': file.filename,
            'file_size': file_size_str,
            'file_type': file_type,
            'mime_type': mimetypes.guess_type(file.filename)[0]
        })
    
    return jsonify({'error': 'File type not allowed'}), 400

def format_file_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"
