import os
from app import app

# Explicitly bind to PORT 10000
port = int(os.environ.get('PORT', 10000))
app.config['PORT'] = port

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=port) 