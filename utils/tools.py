import pickle
import re
import typing as t
import requests
import os
import glob
import fnmatch
import json
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

try:
    import tiktoken
except ImportError:
    tiktoken = None

try:
    import transformers
except ImportError:
    transformers = None

import yaml
sys.path.append(str(Path(__file__).resolve().parents[1]))  # 将父级目录加入执行目录列表

from prompt.summary.summary import CODE_SUMMARY_SYSTEM_PROMPT, CODE_SUMMARY_USER_PROMPT


from data_process.PR.llm_process_3 import llm_restructure_pr_body
# DIFF_URL = "https://github.com/{owner}/{repo}/pull/{pull_number}.diff"

class Agent_utils:

    def __init__(self, config):
        self.config = config
        self.DIFF_URL = self.config['Agent']['diff_url']

        self.headers = {
            'Accept': 'application/vnd.github.v3+json',
        }
        token = os.environ.get('GITHUB_TOKEN')
        if token:
            self.headers['Authorization'] = f'token {token}'

    class DiffFormatter:
        def __init__(self, diff_text, current_file):
            self.diff_text = diff_text
            self.formatted_files = []
            self.current_file = current_file

        def parse_and_format(self):
            """Parse the diff and return a structured format suitable for an AI review agent."""

            current_chunk = None
            lines = self.diff_text.split("\n")

            current_file = {
                "file_path": self.current_file,
                "chunks": [],
            }

            if current_file:
                self.formatted_files.append(current_file)

            for line in lines:
                # New file
                # if line.startswith("diff --git"):
                #     if current_file:
                #         self.formatted_files.append(current_file)
                #     current_file = {
                #         "file_path": self._extract_file_path(line),
                #         "chunks": [],
                #     }

                # File metadata (index, mode changes etc)
                if (
                    line.startswith("index ")
                    or line.startswith("new file")
                    or line.startswith("deleted file")
                ):
                    if current_file:
                        current_file["metadata"] = line

                # Chunk header
                elif line.startswith("@@"):
                    if current_file:
                        current_chunk = self._parse_chunk_header(line)
                        current_file["chunks"].append(current_chunk)

                # Content lines
                elif current_chunk is not None and current_file is not None:
                    if line.startswith("+"):
                        current_chunk["changes"].append(
                            {
                                "type": "addition",
                                "content": line[1:],
                                "new_line_number": current_chunk["new_line"],
                            }
                        )
                        current_chunk["new_line"] += 1
                    elif line.startswith("-"):
                        current_chunk["changes"].append(
                            {
                                "type": "deletion",
                                "content": line[1:],
                                "old_line_number": current_chunk["old_line"],
                            }
                        )
                        current_chunk["old_line"] += 1
                    elif line.startswith("\\"):
                        # Handle "No newline at end of file" cases
                        continue
                    else:  # Context line
                        current_chunk["changes"].append(
                            {
                                "type": "context",
                                "content": line[1:] if line.startswith(" ") else line,
                                "old_line_number": current_chunk["old_line"],
                                "new_line_number": current_chunk["new_line"],
                            }
                        )
                        current_chunk["old_line"] += 1
                        current_chunk["new_line"] += 1

            if current_file:
                self.formatted_files.append(current_file)

            return self.format_for_agent()

        def _extract_file_path(self, diff_header):
            """Extract the file path from diff header line."""
            parts = diff_header.split(" ")
            return parts[-1].lstrip("a/").lstrip("b/")

        def _parse_chunk_header(self, header):
            """Parse the @@ line to get the line numbers."""
            # Example: @@ -1,7 +1,6 @@
            parts = header.split(" ")
            old_start = int(parts[1].split(",")[0].lstrip("-"))
            new_start = int(parts[2].split(",")[0].lstrip("+"))

            return {
                "header": header,
                "old_start": old_start,
                "new_start": new_start,
                "old_line": old_start,
                "new_line": new_start,
                "changes": [],
            }

        def format_for_agent(self):
            """Format the parsed diff in a clear, AI-friendly format."""
            formatted_output = []

            for file in self.formatted_files:
                file_info = f"\nFile: {file['file_path']}\n"
                if "metadata" in file:
                    file_info += f"Metadata: {file['metadata']}\n"
                formatted_output.append(file_info)

                for chunk in file["chunks"]:
                    formatted_output.append(f"\nChunk {chunk['header']}")
                    max_line_number_length = max(
                        [
                            len(str(change["new_line_number"]))
                            for change in chunk["changes"]
                            if change["type"] != "deletion"
                        ]
                    )
                    for change in chunk["changes"]:
                        if change["type"] == "addition":
                            line_info = f"+ {change['new_line_number']}"
                            line_info = line_info.rjust(max_line_number_length + 2)
                        elif change["type"] == "deletion":
                            line_info = " "
                            line_info = "-" + line_info.rjust(max_line_number_length + 1)
                        else:
                            line_info = f" {change['new_line_number']}"
                            line_info = line_info.rjust(max_line_number_length + 2)
                        # spaces = ' ' * (15 - len(line_info))
                        spaces = ""
                        formatted_output.append(f"{line_info}{spaces}: {change['content']}")

            return "\n".join(formatted_output)

        def get_structured_diff(self):
            """Return the structured diff data for programmatic use."""
            return self.formatted_files

    def search_entity_in_project(self, entity_name: str) -> t.Dict:

        """
        Search for information about an entity (class or function) from the code knowledge graph. The entity information includes entity name, entity type, file to which it belongs, and number of lines in the file.

        :param entity_name: The name of the entity (class or function) to be queried.
        :param thought: Thought to be used for the request.

        :return entity_detail: The entity detail includes entity name, entity type, file to which it belongs, and number of lines in the file.
        """
        try:
            with open(f"{self.config['CKG']['graph_pkl_dir']}", 'rb') as f:
                CKG = pickle.load(f)

            if entity_name in CKG:
                # 获取节点的属性
                node_attributes = CKG.nodes[entity_name]
                node_attributes.pop('references')
                # print(f"节点 {entity_name} 的属性：", node_attributes)
                return json.dumps({"detail_of_entity": node_attributes})

            return json.dumps({"error": "cat not find the entity (class or function) in the project"})
        except FileNotFoundError:
            return json.dumps({"error": "Code knowledge graph file not found"})
        except pickle.PickleError:
            return json.dumps({"error": "Failed to load code knowledge graph"})
        except KeyError:
            return json.dumps({"error": f"Entity '{entity_name}' exists but has invalid structure"})
        except Exception as e:
            return json.dumps({"error": f"An unexpected error occurred while searching entity: {str(e)}"})

    def search_code_dependencies(self, entity_name: str) -> t.Dict:
        """
        Searches for entities that points to an entity or to which an entity points.

        :param entity_name: Entity name to search.
        :param in_or_out: `in` means searching for other entities pointing to this entity, and `out` means searching for other entities pointed to by this entity.
        :param thought: Thought to be used for the request.

        :return neighbors: Neighbors of the entity.
        """
        try:
            with open(f"{self.config['CKG']['graph_pkl_dir']}", 'rb') as f:
                CKG = pickle.load(f)

            neighbors = {}
            if entity_name in CKG:
                neighbors['entities_that_CALL_the_target_entity'] = list(CKG.predecessors(entity_name))
                neighbors['entities_CALLED_by_the_target_entity'] = list(CKG.neighbors(entity_name))
                return json.dumps(neighbors)

            return json.dumps({"error": "cat not find the entity in code knowledge graph"})
        except FileNotFoundError:
            return json.dumps({"error": "Code knowledge graph file not found"})
        except pickle.PickleError:
            return json.dumps({"error": "Failed to load code knowledge graph"})
        except Exception as e:
            return json.dumps({"error": f"An unexpected error occurred while searching dependencies: {str(e)}"})

    def search_files_path_by_pattern(self, pattern, cursor=0, page_size=100):
        try:
            cur_work_dir = os.getcwd()

            if not os.path.isabs(pattern):
                pattern = os.path.join(cur_work_dir, '**', pattern)

            matched_pattern = glob.glob(pattern, recursive=True)

            # 计算起始和结束索引
            start_index = cursor * page_size
            end_index = start_index + page_size

            # 切片获取当前页的结果
            current_page_results = matched_pattern[start_index:end_index]

            # 构建结果
            path_list = [{"path": file} for file in current_page_results]

            # 添加分页元数据
            result = {
                "data": path_list,
                "pagination": {
                    "total": len(matched_pattern),
                    "cursor": cursor,
                    "page_size": page_size,
                    "has_more": end_index < len(matched_pattern)
                }
            }
            if len(path_list) == 0:
                return json.dumps({"error": "No files found matching the pattern."})
            return json.dumps(result)
        except Exception as e:
            return json.dumps({"error": f"An error occurred while searching files: {str(e)}"})

    def view_file_contents(self, file_path, index=0, start_line=None, end_line=None):
        def get_target_content(start_line, end_line, all_lines):
            if start_line is not None and end_line is not None:
                start_idx = max(0, start_line - 1)
                end_idx = min(end_line, len(all_lines))
                file_content = ''.join(all_lines[start_idx:end_idx])
                return json.dumps({"file_content": file_content})
            else:
                lines_per_chunk = 500
                start_idx = index * lines_per_chunk
                end_idx = min(start_idx + lines_per_chunk, len(all_lines))
                if start_idx >= len(all_lines):
                    return f"Index out of range. File has {len(all_lines)} lines."
                file_content = ''.join(all_lines[start_idx:end_idx])
                return json.dumps({"file_content": file_content})

        if os.path.isdir(file_path):
            return json.dumps({"error": "The provided path is a directory, not a file."})

        diff_list = json.loads(requests.get(self.DIFF_URL, headers=self.headers).text)
        for diff in diff_list:
            if  diff['filename'] in file_path:
                raw_file_url = diff['raw_url']
                file_content = requests.get(raw_file_url, headers=self.headers).text
                file_lines = [line + '\n' for line in file_content.split('\n')]
                return get_target_content(start_line, end_line, file_lines)

        if self.config['CKG']['project_dir'] not in file_path:
            file_path = os.path.join(self.config['CKG']['project_dir'], file_path)
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                file_lines = file.readlines()
                return get_target_content(start_line, end_line, file_lines)
        except FileNotFoundError:
            return json.dumps({"error": f"File not found: {file_path}"})
        except PermissionError:
            return json.dumps({f"Permission denied: {file_path}"})
        except UnicodeDecodeError:
            return json.dumps({f"Unable to decode file: {file_path}. The file may be binary or use an unsupported encoding."})
        except Exception as e:
            return json.dumps({f"An error occurred: {e}. A valid relative file path is required."})

    def view_code_changes(self, file_path, if_full=False):
        try:
            diff_list = json.loads(requests.get(self.DIFF_URL, headers=self.headers).text)
            if if_full:
                formatted_patch_list = []
                for diff in diff_list:
                    patch = diff['patch']
                    formatted_patch = self.DiffFormatter(patch, diff['filename']).parse_and_format()
                    formatted_patch_list.append(formatted_patch)
                return json.dumps({'code_changes':'\n'.join(formatted_patch_list)})
            else:
                for diff in diff_list:
                    if diff['filename'] == file_path:
                        patch = diff['patch']
                        formatted_patch = self.DiffFormatter(patch, file_path).parse_and_format()
                        return json.dumps({'code_changes': formatted_patch})
            return json.dumps({"error": 'File not found in diff list. A path relative to the repo root is required.'})
        except requests.RequestException as e:
            return json.dumps({"error": f"Failed to retrieve diff information: {str(e)}"})
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON response from diff URL"})
        except KeyError as e:
            return json.dumps({"error": f"Missing key in diff data: {str(e)}"})
        except Exception as e:
            return json.dumps({"error": f"An unexpected error occurred while viewing code changes: {str(e)}"})
    def list_directory_contents(self, directory_path):
        try:
            cur_work_dir = os.getcwd()
            print(f"cur_work_dir is {cur_work_dir}")

            # 处理相对路径和绝对路径
            if not os.path.isabs(directory_path):
                target_path = os.path.join(cur_work_dir, directory_path)
            else:
                target_path = directory_path

            # 规范化路径
            target_path = os.path.normpath(target_path)

            # 检查目录是否存在
            if not os.path.exists(target_path):
                return json.dumps({"error": f"Directory does not exist: {directory_path}"})

            if not os.path.isdir(target_path):
                return json.dumps({"error": f"Path is not a directory: {directory_path}"})

            # 获取目录内容
            contents = []
            try:
                for item in os.listdir(target_path):
                    item_path = os.path.join(target_path, item)

                    item_info = {
                        "name": item,
                        "path": os.path.relpath(item_path, cur_work_dir),
                        "type": "directory" if os.path.isdir(item_path) else "file"
                    }
                    contents.append(item_info)
            except PermissionError:
                return json.dumps({"error": f"Permission denied to access directory: {directory_path}"})

            # 按类型和名称排序（目录在前，然后按名称排序）
            contents.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))

            result = {
                "directory_path": directory_path,
                "resolved_path": os.path.relpath(target_path, cur_work_dir),
                "contents": contents,
                "total_items": len(contents),
                "directories": len([item for item in contents if item["type"] == "directory"]),
                "files": len([item for item in contents if item["type"] == "file"])
            }

            if len(contents) == 0:
                return json.dumps({"message": "Directory is empty.", **result})

            return json.dumps(result)

        except Exception as e:
            return json.dumps({"error": f"An error occurred while listing directory contents: {str(e)}"})

    def get_code_changes_summary(self):
        print("starting to get code changes summary...")

        def build_lightweight_summary(diff_list):
            summaries = []
            for pr_file_data in diff_list:
                patch = pr_file_data.get('patch') or ''
                if len(patch) > 12000:
                    patch = patch[:12000] + "\n... [patch truncated]"
                summaries.append({
                    'filename': pr_file_data.get('filename'),
                    'status': pr_file_data.get('status'),
                    'additions': pr_file_data.get('additions'),
                    'deletions': pr_file_data.get('deletions'),
                    'changes': pr_file_data.get('changes'),
                    'patch': patch,
                })
            return summaries

        try:
            if os.path.exists(self.config['Summary']['code_summary_file_path']):
                with open(self.config['Summary']['code_summary_file_path'], 'r') as f:
                    code_summary = json.load(f)
            else:
                code_summary = {}

            repo = self.config['Judge']['repo']
            pull_number = self.config['Judge']['pull_number']
            if repo in code_summary:
                repo_code_summary = code_summary[repo]
                if pull_number in repo_code_summary:
                    repo_code_summary_pull_number = repo_code_summary[pull_number]
                    return json.dumps({'code_changes_summary':repo_code_summary_pull_number})
            else:
                code_summary[repo] = {}

            response = requests.get(self.DIFF_URL, headers=self.headers, timeout=60)
            response.raise_for_status()
            diff_list = response.json()
            pr_code_summary = build_lightweight_summary(diff_list)
            code_summary[repo][pull_number] = pr_code_summary

            summary_dir = os.path.dirname(self.config['Summary']['code_summary_file_path'])
            if summary_dir:
                os.makedirs(summary_dir, exist_ok=True)
            with open(self.config['Summary']['code_summary_file_path'], 'w') as f:
                json.dump(code_summary, f)
            return json.dumps({'code_changes_summary': pr_code_summary})
        except Exception as e:
            return json.dumps({"error": f"An unexpected error occurred while getting code changes summary: {str(e)}"})

    def reformat_pr_info_for_user_prompt(self):
        print("starting reformat PR info for user prompt...")

        tmp_dir = self.config['Judge']['tmp_dir']
        tmp_path = os.path.join(tmp_dir, f"{self.config['Judge']['pull_number']}_PR_body.json")

        # 查看是否存在tmp_path文件
        if os.path.exists(tmp_path):
            with open(tmp_path, 'r') as f:
                return json.load(f)
        else:
            os.makedirs(tmp_dir, exist_ok=True)
            tmp_path = os.path.join(tmp_dir, f"{self.config['Judge']['pull_number']}_PR_body.json")

        body = None
        title = None
        PR_url = self.config['Agent']['PR_url']
        response = requests.get(PR_url, headers=self.headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        body = data.get('body') or ''
        title = data.get('title') or ''
        escaped_body = body.replace("\r\n", "\\n").replace('\"', ' \\"').replace("'", "\'").replace("\t", "\\t")
        escaped_body = self.fix_invalid_json_escapes(escaped_body)

        try:
            result = llm_restructure_pr_body(self.config, escaped_body)
            if '```json' in result:
                pattern = r"```json\s*(\{[\s\S]*?\})\s*```"
                match = re.search(pattern, result)
                if not match:
                    raise ValueError("Could not find JSON block in PR restructure response")
                dict_result = json.loads(match.group(1))
            else:
                dict_result = json.loads(result)
        except Exception as e:
            print(f"Warning: failed to restructure PR body with LLM, using raw body. Error: {e}")
            dict_result = {
                "Description of changes": body,
                "Test plan": "None",
            }

        dict_result["Description of changes"] = title + '\n' + dict_result.get("Description of changes", "")

        PR_Files_url = self.config['Agent']['diff_url']
        response = requests.get(PR_Files_url, headers=self.headers, timeout=60)

        if response.status_code == 200:
            PR_Changed_Files = response.json()
            for file in PR_Changed_Files:
                file.pop('sha', None)
                file.pop('blob_url', None)
                file.pop('raw_url', None)
                file.pop('contents_url', None)
                file.pop('patch', None)
        else:
            response.raise_for_status()


        tmp_info = {
            'PR_Content': dict_result["Description of changes"],
            'PR_Changed_Files': PR_Changed_Files,
            'Test_Plan': dict_result.get("Test plan", "None")
        }
        with open(f"{tmp_path}", 'w') as f:
            json.dump(tmp_info, f)

        return tmp_info
    def fix_invalid_json_escapes(self, json_str):
        # 有效的JSON转义序列
        valid_escapes = ['"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u']

        # 查找所有反斜杠后跟着的字符
        def replace_invalid_escape(match):
            escape_char = match.group(1)
            # 如果是有效的转义序列，保留它
            if escape_char in valid_escapes:
                return '\\' + escape_char
            # 如果是无效的转义序列，在反斜杠前再加一个反斜杠使其成为字面量
            else:
                return '\\\\' + escape_char

        # 使用正则表达式查找和替换所有转义序列
        fixed_str = re.sub(r'\\([^"])', replace_invalid_escape, json_str)


        return fixed_str

    def explore_project_structure(
        self,
        root_path: str,
        max_depth: int = 3,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> str:
        """
        Explore and return the project file structure as either JSON or a formatted tree.

        Args:
            root_path (str): The starting directory path to explore
            max_depth (int, optional): Maximum depth of directories to display. Defaults to 3.
            include_patterns (List[str], optional): List of patterns to include. Defaults to None.
            exclude_patterns (List[str], optional): List of patterns to exclude. Defaults to None.

        Returns:
            str: Project structure in the requested format or error message
        """
        if not os.path.exists(root_path):
            return f"Error: Path '{root_path}' does not exist."

        if not os.path.isdir(root_path):
            return f"Error: Path '{root_path}' is not a directory."

        if include_patterns is None:
            include_patterns = ["*"]

        if exclude_patterns is None:
            exclude_patterns = []

        def should_include(path: str) -> bool:
            """Determine if a path should be included based on patterns."""
            filename = os.path.basename(path)

            for pattern in exclude_patterns:
                if os.path.sep in pattern:
                    if fnmatch.fnmatch(path, pattern):
                        return False
                if fnmatch.fnmatch(filename, pattern):
                    return False

            if os.path.isdir(path) and not any(os.path.sep in p for p in include_patterns):
                return True

            for pattern in include_patterns:
                if os.path.sep in pattern:
                    if fnmatch.fnmatch(path, pattern):
                        return True
                elif fnmatch.fnmatch(filename, pattern):
                    return True

            return False

        # Generate JSON format structure
        def generate_json_structure() -> str:
            """Generate directory structure in JSON format."""
            def build_structure(dir_path: str, current_depth: int = 0) -> Dict[str, Any]:
                """Recursively build a dictionary representing the directory structure."""
                name = os.path.basename(dir_path)
                result = {
                    "name": name if name else dir_path,  # Handle root directory
                    "type": "directory",
                    "path": dir_path,
                    "children": []
                }

                if current_depth > max_depth:
                    result["note"] = "max depth reached"
                    return result

                try:
                    entries = os.listdir(dir_path)

                    # Sort entries: directories first, then files
                    dirs = [e for e in entries if os.path.isdir(os.path.join(dir_path, e))
                            and should_include(os.path.join(dir_path, e))]
                    files = [e for e in entries if os.path.isfile(os.path.join(dir_path, e))
                            and should_include(os.path.join(dir_path, e))]

                    dirs.sort()
                    files.sort()

                    # Process directories
                    for d in dirs:
                        path = os.path.join(dir_path, d)
                        child = build_structure(path, current_depth + 1)
                        result["children"].append(child)

                    # Process files
                    for f in files:
                        path = os.path.join(dir_path, f)
                        file_info = {
                            "name": f,
                            "type": "file",
                            "path": path
                        }
                        result["children"].append(file_info)

                except PermissionError:
                    result["error"] = "Permission denied"
                except Exception as e:
                    result["error"] = str(e)

                return result

            # Build the structure starting from root_path
            structure = build_structure(root_path)
            return json.dumps(structure, indent=2)

        return generate_json_structure()
    def cal_deepseek_token(text):
        try:
            if transformers is None:
                return None
            chat_tokenizer_dir = "./utils/deepseek_v3_tokenizer"

            tokenizer = transformers.AutoTokenizer.from_pretrained(
                    chat_tokenizer_dir, trust_remote_code=True
                    )

            result = tokenizer.encode(text)
            return len(result)
        except Exception as e:
            print(f"Error calculate token for deepseek: {e}")
            return None
    def cal_gpt_token(text):
        try:
            if tiktoken is None:
                return None
            enc = tiktoken.get_encoding("cl100k_base")  # 可以根据需要选择不同的编码器，如 "gpt2"、"cl100k_base" 等
            tokens = enc.encode(text)
            return len(tokens)
        except Exception as e:
            print(f"Error calculate token for gpt: {e}")
            return None
    def cal_qwen_token(text):
        try:
            if transformers is None:
                return None
            chat_tokenizer_dir = "./utils/qwen_tokenizer"

            tokenizer = transformers.AutoTokenizer.from_pretrained(
                    chat_tokenizer_dir, trust_remote_code=True
                    )

            result = tokenizer.encode(text)
            return len(result)
        except Exception as e:
            print(f"Error calculate token for qwen: {e}")
            return None
def main():

    content = Agent_utils.list_directory_contents("./test_project")
    print(content)

if __name__ == '__main__':
    main()
