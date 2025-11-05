# Configuration

This directory contains the configuration files for StepFly.

## Files

- **config.json**: Your actual configuration file (gitignored)
- **incident_tsg_map.json**: Maps incident IDs to TSG files

## Setup

1. Copy the configuration template:
   ```bash
   # The config.json should already exist with default values
   # Just update it with your API key
   ```

2. Edit `config.json` and add your OpenAI API key:
   ```json
   {
     "llm": {
       "api_base": "https://api.openai.com/v1",
       "api_key": "your-actual-api-key-here",
       "model": "gpt-4o-mini"
     }
   }
   ```

3. **Important**: `config.json` is in `.gitignore` to protect your API key.

## Configuration Options

### LLM Settings
- `api_base`: API endpoint URL
- `api_key`: Your API key
- `model`: Model name (e.g., gpt-4o-mini, gpt-4)

### Memory Database
- `host`: MongoDB host (default: localhost)
- `port`: MongoDB port (default: 27017)
- `reset_on_start`: Clear database on startup (true/false)

### Tools
- `enable_plugins`: Enable/disable plugin system
- `tsg_loader`: TSG document paths
- `code_interpreter`: Code execution settings

For more details, see the main [README.md](../README.md).

