from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import os
import difflib
import re

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {
    'py': 'Python',
    'go': 'Go',
    'java': 'Java',
    'c': 'C',
    'cpp': 'C++',
    'cs': 'C#',
    'js': 'JavaScript',
    'jsx': 'JavaScript',
    'ts': 'TypeScript',
    'tsx': 'TypeScript'
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_extension(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

def normalize_code(code):
    """Remove comments and extra whitespace for better comparison"""
    # Remove single-line comments
    code = re.sub(r'//.*?$', '', code, flags=re.MULTILINE)
    code = re.sub(r'#.*?$', '', code, flags=re.MULTILINE)
    # Remove multi-line comments
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    # Remove extra whitespace
    code = re.sub(r'\s+', ' ', code)
    return code.strip()

def calculate_similarity(code1, code2):
    """Calculate similarity using multiple metrics"""
    # Method 1: Direct sequence matching
    seq_similarity = difflib.SequenceMatcher(None, code1, code2).ratio()
    
    # Method 2: Normalized code comparison (removes comments/whitespace)
    norm1 = normalize_code(code1)
    norm2 = normalize_code(code2)
    norm_similarity = difflib.SequenceMatcher(None, norm1, norm2).ratio()
    
    # Method 3: Line-by-line comparison
    lines1 = code1.splitlines()
    lines2 = code2.splitlines()
    line_similarity = difflib.SequenceMatcher(None, lines1, lines2).ratio()
    
    # Method 4: Token-based similarity
    tokens1 = set(re.findall(r'\b\w+\b', code1))
    tokens2 = set(re.findall(r'\b\w+\b', code2))
    if tokens1 or tokens2:
        token_similarity = len(tokens1 & tokens2) / len(tokens1 | tokens2)
    else:
        token_similarity = 0
    
    # Weighted average
    final_similarity = (
        seq_similarity * 0.3 +
        norm_similarity * 0.3 +
        line_similarity * 0.2 +
        token_similarity * 0.2
    )
    
    return {
        'overall': round(final_similarity * 100, 2),
        'sequence': round(seq_similarity * 100, 2),
        'normalized': round(norm_similarity * 100, 2),
        'line_based': round(line_similarity * 100, 2),
        'token_based': round(token_similarity * 100, 2)
    }

def detect_ai_generated(code):
    """Analyze code patterns that might indicate AI generation"""
    indicators = {
        'comment_density': 0,
        'perfect_indentation': 0,
        'generic_names': 0,
        'documentation_style': 0,
        'complexity': 0
    }
    
    lines = code.splitlines()
    total_lines = len(lines)
    
    if total_lines == 0:
        return {'probability': 0, 'confidence': 'low', 'indicators': indicators}
    
    # Check comment density
    comment_lines = len([l for l in lines if l.strip().startswith(('#', '//', '/*', '*'))])
    indicators['comment_density'] = round((comment_lines / total_lines) * 100, 2)
    
    # Check indentation consistency
    indented_lines = [l for l in lines if l.startswith((' ', '\t'))]
    if indented_lines:
        indent_lengths = [len(l) - len(l.lstrip()) for l in indented_lines]
        # Check if indentation is very consistent (typical of AI)
        if indent_lengths and len(set(indent_lengths)) <= 3:
            indicators['perfect_indentation'] = 80
        else:
            indicators['perfect_indentation'] = 30
    
    # Check for generic variable names
    generic_patterns = r'\b(var|temp|data|result|value|item|element|obj|arr)\d*\b'
    generic_count = len(re.findall(generic_patterns, code, re.IGNORECASE))
    indicators['generic_names'] = min(generic_count * 10, 100)
    
    # Check documentation style
    doc_patterns = r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|/\*\*[\s\S]*?\*/)'
    doc_blocks = re.findall(doc_patterns, code)
    indicators['documentation_style'] = min(len(doc_blocks) * 20, 100)
    
    # Check code complexity (simpler = more likely AI)
    avg_line_length = sum(len(l) for l in lines) / total_lines if total_lines > 0 else 0
    if avg_line_length < 30:
        indicators['complexity'] = 30
    elif avg_line_length < 50:
        indicators['complexity'] = 50
    else:
        indicators['complexity'] = 70
    
    # Calculate overall probability
    probability = sum(indicators.values()) / (len(indicators) * 100) * 100
    
    # Determine confidence level
    if probability > 70:
        confidence = 'high'
    elif probability > 40:
        confidence = 'medium'
    else:
        confidence = 'low'
    
    return {
        'probability': round(probability, 2),
        'confidence': confidence,
        'indicators': indicators
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        # Check if files are present
        if 'file1' not in request.files or 'file2' not in request.files:
            return jsonify({'error': 'Both files are required'}), 400
        
        file1 = request.files['file1']
        file2 = request.files['file2']
        
        # Check if files are selected
        if file1.filename == '' or file2.filename == '':
            return jsonify({'error': 'Please select both files'}), 400
        
        # Check file extensions
        ext1 = get_file_extension(file1.filename)
        ext2 = get_file_extension(file2.filename)
        
        if not allowed_file(file1.filename) or not allowed_file(file2.filename):
            return jsonify({
                'error': f'Invalid file type. Allowed: {", ".join(ALLOWED_EXTENSIONS.keys())}'
            }), 400
        
        if ext1 != ext2:
            return jsonify({
                'error': f'File extensions must match. Got: .{ext1} and .{ext2}'
            }), 400
        
        # Read file contents
        code1 = file1.read().decode('utf-8', errors='ignore')
        code2 = file2.read().decode('utf-8', errors='ignore')
        
        # Calculate similarity
        similarity = calculate_similarity(code1, code2)
        
        # Detect AI generation for both files
        ai_detection1 = detect_ai_generated(code1)
        ai_detection2 = detect_ai_generated(code2)
        
        return jsonify({
            'success': True,
            'language': ALLOWED_EXTENSIONS[ext1],
            'extension': ext1,
            'similarity': similarity,
            'ai_detection': {
                'file1': ai_detection1,
                'file2': ai_detection2
            }
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
