from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import os
import difflib
import re
from collections import Counter

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {
    'py': 'Python', 'go': 'Go', 'java': 'Java', 'c': 'C',
    'cpp': 'C++', 'cs': 'C#', 'js': 'JavaScript', 'jsx': 'JavaScript',
    'ts': 'TypeScript', 'tsx': 'TypeScript'
}

# ------------------ Utilities ------------------

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_extension(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

def normalize_code(code):
    """Smart normalization: remove comments, compress whitespaces, fix braces/brackets."""
    # Remove single and multi-line comments
    code = re.sub(r'//.*', '', code)
    code = re.sub(r'#.*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    code = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', '', code, flags=re.DOTALL)
    # Normalize braces and spacing
    code = re.sub(r'[\t ]+', ' ', code)
    code = re.sub(r'\n+', '\n', code)
    code = re.sub(r'[{}()\[\]]', ' ', code)
    return code.strip()

def tokenize(code):
    """Weighted tokenization by frequency — better than simple set matching."""
    tokens = re.findall(r'[A-Za-z_]\w*|\d+|[^\w\s]', code)
    token_counts = Counter(tokens)
    total_count = sum(token_counts.values())
    # Normalize frequencies to percentage
    return {t: c / total_count for t, c in token_counts.items()} if total_count else {}

def calculate_similarity(code1, code2):
    """Enhanced similarity metrics."""
    # Sequence-level
    seq_similarity = difflib.SequenceMatcher(None, code1, code2).ratio()

    # Normalization-level
    norm1 = normalize_code(code1)
    norm2 = normalize_code(code2)
    norm_similarity = difflib.SequenceMatcher(None, norm1, norm2).ratio()

    # Line-level
    lines1 = [l.strip() for l in code1.splitlines() if l.strip()]
    lines2 = [l.strip() for l in code2.splitlines() if l.strip()]
    line_similarity = difflib.SequenceMatcher(None, lines1, lines2).ratio()

    # Token-level (frequency comparison via cosine similarity)
    tokens1, tokens2 = tokenize(code1), tokenize(code2)
    all_tokens = set(tokens1.keys()) | set(tokens2.keys())
    dot = sum(tokens1.get(t, 0) * tokens2.get(t, 0) for t in all_tokens)
    mag1 = sum(v ** 2 for v in tokens1.values()) ** 0.5
    mag2 = sum(v ** 2 for v in tokens2.values()) ** 0.5
    token_similarity = dot / (mag1 * mag2) if mag1 and mag2 else 0

    # Weighted adaptive average
    n_lines = max(len(lines1), len(lines2))
    weight_line = 0.3 if n_lines > 10 else 0.15
    final = (
        seq_similarity * 0.25 +
        norm_similarity * 0.25 +
        line_similarity * weight_line +
        token_similarity * (1 - 0.25 - 0.25 - weight_line)
    )

    return {
        'overall': round(final * 100, 2),
        'sequence': round(seq_similarity * 100, 2),
        'normalized': round(norm_similarity * 100, 2),
        'line_based': round(line_similarity * 100, 2),
        'token_based': round(token_similarity * 100, 2)
    }

# ------------------ AI Detection ------------------

def detect_ai_generated(code):
    """Improved AI pattern detection."""
    indicators = {
        'comment_density': 0,
        'naming_randomness': 0,
        'indent_consistency': 0,
        'readability_balance': 0,
        'complexity': 0
    }
    lines = [l for l in code.splitlines() if l.strip()]
    total_lines = len(lines)
    if total_lines == 0:
        return {'probability': 0, 'confidence': 'low', 'indicators': indicators}

    # Comment density
    comment_lines = len([l for l in lines if l.strip().startswith(('#', '//', '/*'))])
    indicators['comment_density'] = round(comment_lines / total_lines * 100, 2)

    # Naming randomness: presence of vars like a1, tmp2, x99
    rand_vars = re.findall(r'\b[a-z]{1,2}\d+\b', code)
    indicators['naming_randomness'] = min(len(rand_vars) * 8, 100)

    # Indentation consistency
    indents = [len(l) - len(l.lstrip()) for l in lines if l.startswith((' ', '\t'))]
    if indents:
        std_indent = len(set(indents))
        indicators['indent_consistency'] = 80 if std_indent <= 3 else 40

    # Readability balance: average line length
    avg_len = sum(len(l) for l in lines) / total_lines
    indicators['readability_balance'] = 100 - min(avg_len, 100) if avg_len > 60 else 70

    # Complexity heuristic
    token_count = len(re.findall(r'\b\w+\b', code))
    indicators['complexity'] = 30 if token_count < 100 else 60 if token_count < 300 else 80

    # Aggregate probability
    probability = sum(indicators.values()) / (len(indicators) * 100) * 100
    confidence = 'high' if probability > 70 else 'medium' if probability > 40 else 'low'

    return {
        'probability': round(probability, 2),
        'confidence': confidence,
        'indicators': indicators
    }

# ------------------ Flask Routes ------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        if 'file1' not in request.files or 'file2' not in request.files:
            return jsonify({'error': 'Both files are required'}), 400

        file1 = request.files['file1']
        file2 = request.files['file2']

        if file1.filename == '' or file2.filename == '':
            return jsonify({'error': 'Please select both files'}), 400

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

        code1 = file1.read().decode('utf-8', errors='ignore')
        code2 = file2.read().decode('utf-8', errors='ignore')

        similarity = calculate_similarity(code1, code2)
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
