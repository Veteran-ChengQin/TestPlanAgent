import json
import os
import re
import time
import requests
import subprocess
import tempfile
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path

# Try to import tree-sitter and tree-sitter-languages
try:
    from tree_sitter_languages import get_parser, get_language
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    print("tree-sitter-languages not available. Install with: pip install tree-sitter-languages")

class GitDiffProcessor:
    """Process GitHub PR diffs to identify changed code entities"""

    def __init__(self):
        """Initialize the processor"""
        self.parsers = {}
        self.headers = {
            'Accept': 'application/vnd.github.v3+json',
        }
        token = os.environ.get('GITHUB_TOKEN')
        if token:
            self.headers['Authorization'] = f'token {token}'
        if TREE_SITTER_AVAILABLE:
            self._setup_parsers()

    def _setup_parsers(self):
        """Setup tree-sitter parsers for different languages"""
        if not TREE_SITTER_AVAILABLE:
            return

        # Initialize parsers for different languages
        self.parsers = {
            'py': get_parser('python'),
            'js': get_parser('javascript'),
            'ts': get_parser('typescript'),
            'tsx': get_parser('tsx')
        }

    def get_file_from_github(self, raw_url: str) -> str:
        """Get file content from a GitHub raw URL"""
        response = requests.get(raw_url, headers=self.headers)
        response.raise_for_status()
        return response.text

    def reverse_patch(self, patch: str) -> str:
        """Reverse a git patch by swapping addition and deletion markers"""
        reversed_lines = []
        for line in patch.splitlines():
            if line.startswith('+'):
                reversed_lines.append('-' + line[1:])
            elif line.startswith('-'):
                reversed_lines.append('+' + line[1:])
            else:
                reversed_lines.append(line)
        return '\n'.join(reversed_lines)

    def apply_patch_using_cmd(self, content: str, patch: str) -> str:
        """Apply a patch to content using patch command"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create content file
            content_path = os.path.join(temp_dir, 'file.txt')
            with open(content_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # Create patch file
            patch = """--- file.txt\n+++ file.txt\n""" + patch

            patch_lines = patch.splitlines()
            fixed_patch = '\n'.join(patch_lines) + '\n'

            patch_path = os.path.join(temp_dir, 'patch.diff')
            with open(patch_path, 'w', encoding='utf-8') as f:
                f.write(fixed_patch)

            # Apply patch
            try:
                # 使用 shell=True 来允许使用重定向
                cmd = f"patch -R {content_path} < {patch_path}"
                subprocess.run(
                    cmd,
                    shell=True,  # 开启 shell 支持重定向
                    cwd=temp_dir,
                    check=True,
                    capture_output=True
                )


                # 读取打补丁后的内容
                with open(content_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except subprocess.CalledProcessError as e:
                raise Exception(f"应用补丁失败: {e.stderr.decode('utf-8')}")

    def manual_apply_patch(self, content: str, patch: str) -> str:
        """Manually apply a patch when git command fails"""
        content_lines = content.splitlines()
        result_lines = content_lines.copy()

        # Parse the patch to get the hunks
        hunks = []
        current_hunk = None

        for line in patch.splitlines():
            if line.startswith('@@'):
                # Parse the hunk header
                # Example: @@ -10,6 +10,7 @@
                match = re.match(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@', line)
                if match:
                    old_start, old_count, new_start, new_count = map(int, match.groups())
                    current_hunk = {
                        'old_start': old_start - 1,  # 0-based indexing
                        'old_count': old_count,
                        'new_start': new_start - 1,  # 0-based indexing
                        'new_count': new_count,
                        'lines': []
                    }
                    hunks.append(current_hunk)
            elif current_hunk is not None:
                current_hunk['lines'].append(line)

        # Apply hunks in reverse order to avoid index shifting issues
        hunks.reverse()

        for hunk in hunks:
            old_start = hunk['old_start']
            old_lines = [line[1:] if line.startswith('-') or line.startswith('+') else line[1:]
                        for line in hunk['lines'] if line.startswith(' ') or line.startswith('-')]

            # Replace the lines in the result
            result_lines[old_start:old_start + hunk['old_count']] = old_lines

        return '\n'.join(result_lines)

    def parse_with_tree_sitter(self, content: str, file_extension: str) -> dict:
        """Parse code using tree-sitter to get AST"""
        if not TREE_SITTER_AVAILABLE or file_extension not in self.parsers:
            # Fall back to simple regex parsing if tree-sitter isn't available
            return self._simple_parse(content)

        # Use the appropriate parser for the file type
        parser = self.parsers[file_extension]
        tree = parser.parse(content.encode('utf-8'))

        # Process the tree to extract functions and classes
        entities = self._process_tree(tree.root_node, content.encode('utf-8'), file_extension)

        return {'entities': entities}

    def _process_tree(self, node, content: bytes, file_type: str) -> List[dict]:
        """Extract functions and classes from tree-sitter AST"""
        items = []

        def get_node_text(node):
            """Get the source code text for a node"""
            return content[node.start_byte:node.end_byte].decode('utf8')

        def find_name_node(node, name_type='identifier'):
            """Find the name node in children"""
            for child in node.children:
                if child.type == name_type:
                    return child
            return None

        # Process node based on its type and the programming language
        if file_type in ['ts', 'js', 'tsx']:
            if node.type == 'function_declaration' or node.type == 'method_definition':
                name_node = find_name_node(node)
                if name_node:
                    name = get_node_text(name_node)
                    items.append({
                        'type': 'function',
                        'name': name,
                        'start_line': node.start_point[0],
                        'end_line': node.end_point[0],
                        'content': get_node_text(node)
                    })

            elif node.type == 'class_declaration':
                name_node = find_name_node(node)
                if name_node:
                    name = get_node_text(name_node)
                    items.append({
                        'type': 'class',
                        'name': name,
                        'start_line': node.start_point[0],
                        'end_line': node.end_point[0],
                        'content': get_node_text(node)
                    })

        elif file_type == 'py':
            if node.type == 'function_definition':
                name_node = find_name_node(node)
                if name_node:
                    name = get_node_text(name_node)
                    items.append({
                        'type': 'function',
                        'name': name,
                        'start_line': node.start_point[0],
                        'end_line': node.end_point[0],
                        'content': get_node_text(node)
                    })

            elif node.type == 'class_definition':
                name_node = find_name_node(node)
                if name_node:
                    name = get_node_text(name_node)
                    items.append({
                        'type': 'class',
                        'name': name,
                        'start_line': node.start_point[0],
                        'end_line': node.end_point[0],
                        'content': get_node_text(node)
                    })

        # Recursively process children
        for child in node.children:
            items.extend(self._process_tree(child, content, file_type))

        return items

    def _simple_parse(self, content: str) -> dict:
        """Simple regex-based parsing as a fallback"""
        entities = []
        lines = content.splitlines()

        # Simple regex for Python function/class definitions
        pattern = re.compile(r'^(\s*)(def|class)\s+([^\(:]+)')

        i = 0
        while i < len(lines):
            match = pattern.match(lines[i]) if i < len(lines) else None
            if match:
                indent = len(match.group(1))
                entity_type = match.group(2)
                name = match.group(3).strip()

                # Find the end of this entity
                start_line = i
                i += 1
                while i < len(lines):
                    # Skip empty lines
                    if not lines[i].strip():
                        i += 1
                        continue

                    # Check indent to see if we're out of the current entity
                    indent_match = re.match(r'^(\s*)', lines[i])
                    if lines[i].strip() and indent_match and len(indent_match.group(1)) <= indent:
                        break

                    i += 1

                entities.append({
                    'type': entity_type,
                    'name': name,
                    'start_line': start_line,
                    'end_line': i - 1,
                    'content': '\n'.join(lines[start_line:i])
                })
                continue

            i += 1

        return {'entities': entities}

    def find_changed_entities(self, original_content: str, modified_content: str, file_extension: str) -> List[dict]:
        """Find functions/classes that changed between two versions"""
        # Parse both files
        original_ast = self.parse_with_tree_sitter(original_content, file_extension)
        modified_ast = self.parse_with_tree_sitter(modified_content, file_extension)

        # Compare entities
        original_entities = {e['name']: e for e in original_ast['entities']}
        modified_entities = {e['name']: e for e in modified_ast['entities']}

        changed_entities = []

        # Check for modified/added entities
        for name, entity in modified_entities.items():
            if name in original_entities:
                # Entity exists in both versions - check if it changed
                if entity['content'] != original_entities[name]['content']:
                    changed_entities.append({
                        'change_type': 'modified',
                        'entity_type': entity['type'],
                        'name': name,
                        'content': entity['content'],
                        'lines': (entity['start_line'], entity['end_line'])
                    })
            else:
                # New entity
                changed_entities.append({
                    'change_type': 'added',
                    'entity_type': entity['type'],
                    'name': name,
                    'content': entity['content'],
                    'lines': (entity['start_line'], entity['end_line'])
                })

        # Check for deleted entities
        for name, entity in original_entities.items():
            if name not in modified_entities:
                changed_entities.append({
                    'change_type': 'deleted',
                    'entity_type': entity['type'],
                    'name': name,
                    'content': entity['content'],
                    'lines': (entity['start_line'], entity['end_line'])
                })

        return changed_entities

    def process_pr_file(self, pr_file_data: dict) -> dict:
        """Process a single file in a PR to find changed functions/classes"""
        # Extract file info from PR data
        raw_url = pr_file_data['raw_url']
        patch = pr_file_data.get('patch', '')
        filename = pr_file_data['filename']

        # Determine file extension
        file_extension = filename.split('.')[-1].lower()
        if file_extension not in ['py', 'js', 'ts', 'tsx']:
            return {
                'filename': filename,
                'error': f"Unsupported file type: {file_extension}"
            }

        try:
            # Get the modified file content (as raw_url points to the modified file)
            modified_content = self.get_file_from_github(raw_url)

            # Reverse apply the patch to get the original content
            original_content = None

            try:
                # Try using git command
                # reversed_patch = self.reverse_patch(patch)
                original_content = self.apply_patch_using_cmd(modified_content, patch)
            except Exception as e:
                print(f"Git apply failed: {e}, falling back to manual patch application")
                # Fall back to manual patch application
                # original_content = self.manual_apply_patch(modified_content, patch)

            # Find changed entities
            changed_entities = self.find_changed_entities(original_content, modified_content, file_extension)

            return {
                'filename': filename,
                'original_content': original_content,
                'modified_content': modified_content,
                'changed_entities': changed_entities
            }
        except Exception as e:
            return {
                'filename': filename,
                'error': str(e)
            }

def main():
    """Main function for demonstration usage"""
    # Sample PR file data from the original query
    pr_file_data = {
        "sha": "3650c23120eee29f21af0883f400df96dd3d4fa1",
        "filename": "protocol-designer/src/pages/Designer/ProtocolSteps/Timeline/StepOverflowMenu.tsx",
        "status": "modified",
        "additions": 14,
        "deletions": 0,
        "changes": 14,
        "blob_url": "https://github.com/Opentrons/opentrons/blob/03ecb348339380ae84e80671523b5e21ee7b4474/protocol-designer%2Fsrc%2Fpages%2FDesigner%2FProtocolSteps%2FTimeline%2FStepOverflowMenu.tsx",
        "raw_url": "https://github.com/Opentrons/opentrons/raw/03ecb348339380ae84e80671523b5e21ee7b4474/protocol-designer%2Fsrc%2Fpages%2FDesigner%2FProtocolSteps%2FTimeline%2FStepOverflowMenu.tsx",
        "contents_url": "https://api.github.com/repos/Opentrons/opentrons/contents/protocol-designer%2Fsrc%2Fpages%2FDesigner%2FProtocolSteps%2FTimeline%2FStepOverflowMenu.tsx?ref=03ecb348339380ae84e80671523b5e21ee7b4474",
        "patch": "@@ -19,6 +19,8 @@ import {\n   toggleViewSubstep,\n } from '../../../../ui/steps/actions/actions'\n import {\n+  getBatchEditFormHasUnsavedChanges,\n+  getCurrentFormHasUnsavedChanges,\n   getSavedStepForms,\n   getUnsavedForm,\n } from '../../../../step-forms/selectors'\n@@ -49,6 +51,12 @@ export function StepOverflowMenu(props: StepOverflowMenuProps): JSX.Element {\n     multiSelectItemIds,\n   } = props\n   const { t } = useTranslation('protocol_steps')\n+  const singleEditFormHasUnsavedChanges = useSelector(\n+    getCurrentFormHasUnsavedChanges\n+  )\n+  const batchEditFormHasUnstagedChanges = useSelector(\n+    getBatchEditFormHasUnsavedChanges\n+  )\n   const dispatch = useDispatch<ThunkDispatch<BaseState, any, any>>()\n   const formData = useSelector(getUnsavedForm)\n   const savedStepFormData = useSelector(getSavedStepForms)[stepId]\n@@ -93,6 +101,7 @@ export function StepOverflowMenu(props: StepOverflowMenuProps): JSX.Element {\n         {multiSelectItemIds != null && multiSelectItemIds.length > 0 ? (\n           <>\n             <MenuButton\n+              disabled={batchEditFormHasUnstagedChanges}\n               onClick={() => {\n                 duplicateMultipleSteps()\n                 setStepOverflowMenu(false)\n@@ -117,6 +126,7 @@ export function StepOverflowMenu(props: StepOverflowMenuProps): JSX.Element {\n             )}\n             {isPipetteStep || isThermocyclerProfile ? (\n               <MenuButton\n+                disabled={formData != null}\n                 onClick={() => {\n                   setStepOverflowMenu(false)\n                   dispatch(hoverOnStep(stepId))\n@@ -127,6 +137,7 @@ export function StepOverflowMenu(props: StepOverflowMenuProps): JSX.Element {\n               </MenuButton>\n             ) : null}\n             <MenuButton\n+              disabled={singleEditFormHasUnsavedChanges}\n               onClick={() => {\n                 duplicateStep(stepId)\n                 setStepOverflowMenu(false)\n@@ -166,5 +177,8 @@ const MenuButton = styled.button`\n   &:disabled {\n     color: ${COLORS.grey40};\n     cursor: auto;\n+    &:hover {\n+      background-color: ${COLORS.transparent};\n+    }\n   }\n `"
    }

    # Process the PR file
    processor = GitDiffProcessor()
    result = processor.process_pr_file(pr_file_data)

    # Print the results
    if 'error' in result:
        print(f"Error processing file: {result['error']}")
    else:
        print(f"Processed file: {result['filename']}")
        print("\nChanged Entities:")
        for entity in result['changed_entities']:
            print(f"  - {entity['entity_type']} {entity['name']} ({entity['change_type']})")

        # Optional: Save results to files
        # with open('original_file.py', 'w') as f:
            # f.write(result['original_content'])
        # with open('modified_file.py', 'w') as f:
            # f.write(result['modified_content'])
        # print("\nSaved original and modified files to: original_file.py, modified_file.py")



if __name__ == "__main__":
    main()
