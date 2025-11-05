#!/usr/bin/env python3
"""
StepFly Dashboard Server
Start the web UI for real-time TSG execution monitoring
"""

import os
import sys
import argparse
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ui.web_api import TSGVisualizationAPI

# Create Flask app
app = Flask(__name__, static_folder='static')
CORS(app)  # Enable CORS for all routes

# Global API instance
api_instance = TSGVisualizationAPI()


@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('static', 'index.html')


@app.route('/static/<path:path>')
def send_static(path):
    """Serve static files"""
    return send_from_directory('static', path)


@app.route('/api/session/start', methods=['POST'])
def start_new_session():
    """Start a new TSG execution session"""
    try:
        result = api_instance.start_new_session()
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/session/<session_id>/status')
def get_session_status(session_id):
    """Get real-time session status"""
    try:
        # Check if this is the active session
        if api_instance.session_id != session_id:
            return jsonify({
                'success': False,
                'error': 'Session not found or not active'
            }), 404
        
        return jsonify(api_instance.get_realtime_status())
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/session/<session_id>/scheduler/conversation')
def get_scheduler_conversation(session_id):
    """Get scheduler conversation history"""
    try:
        if api_instance.session_id != session_id:
            return jsonify({
                'success': False,
                'error': 'Session not active'
            }), 404
        
        return jsonify(api_instance.get_scheduler_conversation())
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/session/<session_id>/user-input', methods=['POST'])
def send_user_input(session_id):
    """Send user input to scheduler"""
    try:
        if api_instance.session_id != session_id:
            return jsonify({
                'success': False,
                'error': 'Session not active'
            }), 404
        
        data = request.get_json()
        user_input = data.get('input', '')
        
        if not user_input:
            return jsonify({
                'success': False,
                'error': 'No input provided'
            }), 400
        
        return jsonify(api_instance.send_user_input(user_input))
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/session/<session_id>/edges')
def get_edge_connections(session_id):
    """Get edge connection information"""
    try:
        if api_instance.session_id != session_id:
            return jsonify({
                'success': False,
                'error': 'Session not active'
            }), 404
        
        return jsonify(api_instance.get_edge_connections())
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/session/<session_id>/node/<node_id>/conversation')
def get_node_conversation(session_id, node_id):
    """Get conversation history for a specific node"""
    try:
        if api_instance.session_id != session_id:
            return jsonify({
                'success': False,
                'error': 'Session not active'
            }), 404
        
        return jsonify(api_instance.get_node_conversation(node_id))
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/session/<session_id>/info')
def get_session_info(session_id):
    """Get session information"""
    try:
        if api_instance.session_id != session_id:
            return jsonify({
                'success': False,
                'error': 'Session not active'
            }), 404
        
        return jsonify(api_instance.get_session_info())
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/sessions')
def list_sessions():
    """List active session"""
    try:
        active_sessions = []
        if api_instance.session_id:
            active_sessions = [api_instance.session_id]
        
        return jsonify({
            'success': True,
            'sessions': active_sessions,
            'current_session': api_instance.session_id
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='StepFly Dashboard Server')
    parser.add_argument(
        '--port',
        type=int,
        default=8080,
        help='Port to run the server on (default: 8080)'
    )
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host to bind to (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Run in debug mode'
    )
    
    args = parser.parse_args()
    
    # Print startup information
    print("=" * 60)
    print("🚀 StepFly Dashboard Server")
    print("=" * 60)
    print(f"Starting server on http://{args.host}:{args.port}")
    print()
    print("📌 Instructions:")
    print("1. Open the URL in your browser")
    print("2. Click 'Start New Session' button")
    print("3. Enter the incident ID when prompted")
    print("4. Watch the real-time execution!")
    print()
    print("=" * 60)
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    
    # Run the Flask app
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug
    )


if __name__ == '__main__':
    main()
