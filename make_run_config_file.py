import re
import yaml
import os
import datetime
import argparse
from urllib.parse import urlparse

def generate_config(pr_url, output_file_name, llm_model, api_key, llm_url, output_dir=None):
    parsed_url = urlparse(pr_url)
    path_parts = parsed_url.path.strip('/').split('/')

    if len(path_parts) < 4 or path_parts[-2] != 'pulls':
        raise ValueError("Invalid PR URL format. Expected format: https://api.github.com/repos/{org}/{repo}/pulls/{pr_number}")

    org = path_parts[1]
    repo = path_parts[2]
    pr_number = path_parts[4]

    diff_url = f"https://api.github.com/repos/{org}/{repo}/pulls/{pr_number}/files"

    if output_dir is None:
        output_dir = f'./result/tot_test/{repo}/prompt_v1'

    config = {
        'CKG': {
            'project_dir': f"./test_project/{repo}",
            'graph_pkl_dir': f"./CKG/{repo}_graph.pkl"
        },
        'Agent': {
            'diff_url': diff_url,
            'PR_url': pr_url,
            'llm_model': llm_model,
            'api_key': api_key,
            'llm_url': llm_url,
            'output_dir': output_dir,
            'output_file_name': output_file_name
        },
        'Judge': {
            'tmp_dir': f'./result/tot_test/{repo}/tmp/',
            'pull_number': pr_number
        }
    }

    return config

def save_config(config, output_file='config.yaml'):
    with open(output_file, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

    print(f"Configuration saved to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate YAML configuration for a GitHub PR')
    parser.add_argument('--pr_url', default='https://api.github.com/repos/Opentrons/opentrons/pulls/16571', help='The GitHub PR URL')
    parser.add_argument('--model', default=os.environ.get('LLM_MODEL', 'gpt-5.4-mini'), help='LLM model to use')
    parser.add_argument('--api-key', default=os.environ.get('OPENAI_API_KEY', ''), help='LLM api key')
    parser.add_argument('--api', default=os.environ.get('LLM_API_URL', ''), help='LLM API URL')
    parser.add_argument('--output', default='./source/config.yaml', help='Output YAML file')
    parser.add_argument('--output-dir', help='Custom output directory')
    parser.add_argument('--output-file-name', default='gpt-4o_20250315_121546.txt')
    # claude-3-7-sonnet-20250219
    args = parser.parse_args()

    config = generate_config(args.pr_url, args.output_file_name, args.model, args.api_key, args.api, args.output_dir)
    save_config(config, args.output)
