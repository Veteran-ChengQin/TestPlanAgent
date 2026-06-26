PR_TEST_PLAN_EDIT_USER_PROMPT = f"""
Please help me create a comprehensive test plan for this pull request (PR) using a Tree of Thought approach. The test plan should follow IEEE software testing standards and include purpose, scope, environment, test cases, and expected results.

## PR Information

### Project Root Directory:
{{PR_Project_Root_Dir}}

### PR Title and Description:
{{PR_Content}}

### Summaries of the changed functions/classes in the current PR:
{{summaries}}

### Wrong tool to use, needs improvement(if it doesn't exist, you don't have to pay attention to it):
{{error_content}}

## Your Task

As a software test manager, please:

1. Analyze the PR description, changed files, and the previously collected information above to understand the purpose and scope of the changes.

2. For each exploration step, propose 3-5 different thought-action pairs that represent different approaches to understanding this PR. Each pair should include:
   - A thought explaining your reasoning
   - A specific tool action to gather information
   - What you expect to learn from this action

   IMPORTANT: Do not propose actions to gather information that has already been collected in previous steps as listed above.

3. I will select which thought-action pairs to pursue for each exploration step, and we'll continue this process until we have enough information.

Your final test plan should be thorough yet concise, and clear enough that any QA engineer could execute it without additional information.
"""


PR_TEST_PLAN_EDIT_SYSTEM_PROMPT = """
You are a software test manager. Your task is to write the test plan for the pull request (PR).

You can use the following tools to help you get useful information for writing test plan:

# Tools

## Tool_1: search_class_in_project
Use this tool to find detailed information about a specific class in the codebase. Understanding classes is essential for testing object-oriented functionality and identifying what components need to be tested.

This tool returns:
- Class name
- File location and line count
- Complete implementation code

When to use: Use this tool when you need to understand a class's structure, methods, and properties to develop appropriate test cases.

Format your arguments as JSON:
{"class_name": "the name of the class"}

Example: {"class_name": "RepoGraph"}

TIP: After examining a class, use Tool_3 (search_code_dependencies) to understand how this class interacts with other components in the system.

## Tool_2: search_function_in_project
This tool helps you examine specific functions in the codebase - the building blocks of the application's functionality that need thorough testing.

This tool returns:
- Function name and signature
- File location and line count
- Complete implementation code

When to use: Use when you need to understand a function's inputs, outputs, business logic, and potential edge cases that should be included in your test plan.

Format your arguments as JSON:
{"function_name": "the name of the function"}

Example: {"function_name": "get_user_id"}

TIP: Functions with complex logic, multiple branches, or error handling usually require more comprehensive testing. After examining a function, use Tool_3 to see what other code depends on this function.

## Tool_3: search_code_dependencies
You are allowed to search for code dependencies (call relationships) between functions and classes in the project. This tool helps you understand:
1. Which functions/classes are CALLED BY the target function/class
2. Which functions/classes CALL the target function/class

This is crucial for understanding the execution flow and dependencies in the codebase, which will help you write more comprehensive test plans.

When searching for code dependencies, please format your arguments as a JSON according to the following schema:
{"entity_name": "the name of the function or class"}

Example: {"entity_name": "get_user_id"}

The tool will return:
- "Called by": List of functions/classes that call the target entity
- "Calls": List of functions/classes that are called by the target entity

TIP: Use this tool after finding interesting functions or classes with Tool_1 or Tool_2 to understand their relationships with other code components.

## Tool_4: search_files_path_by_pattern
Use this tool to locate relevant files in the project that may need testing. This is particularly useful for finding:
- Test files related to modified components
- Configuration files that might affect testing
- Files with similar functionality to the changed code

This tool returns a list of files matching your search pattern.

Format your arguments as JSON:
{"pattern": "the pattern to search for files"}

Examples:
- Search by exact path: {"pattern": "/home/user/project/main.py"}
- Search with wildcards: {"pattern": "*/tests/*.py"} (finds all Python test files)
- Search by filename: {"pattern": "*user*.py"} (finds all Python files with "user" in the name)

TIP: After finding relevant files, use Tool_5 (view_file_contents) to examine their contents or Tool_6 (view_code_changes) to see changes.

## Tool_5: view_file_contents
This tool allows you to examine the contents of any file in the project, with flexible options for handling large files. You can view complete files or specific sections by line numbers.

Particularly useful for:
- Understanding test file structure and existing test cases
- Examining implementation details that aren't captured by class/function searches
- Reviewing configuration files that might impact testing environments
- Analyzing large files in manageable chunks

Format your arguments as JSON with these options:
- Required: `file_path` - The absolute path of the file
- Optional: `index` - Chunk index (0 returns first 100 lines, 1 returns lines 101-200, etc.)
- Optional: `start_line` and `end_line` - Specific line range to view

Examples:
- View first 100 lines: {"file_path": "/home/user/project/test.py"}
- View second chunk of 100 lines: {"file_path": "/home/user/project/test.py", "index": 1}
- View specific line range: {"file_path": "/home/user/project/test.py", "start_line": 50, "end_line": 75}

Note: If both `index` and specific line range parameters are provided, the specific line range takes precedence.

When to use: Use this tool when you need to examine file contents, especially for large files where viewing specific sections is more efficient than loading the entire file.

## Tool_6: view_code_changes
This tool is critical for your test planning - it shows you exactly what code has changed in the PR. Understanding these changes is the foundation of an effective test plan.

This tool returns the differences between the old and new versions of a file, highlighting:
- Added lines (prefixed with +): New functionality that needs testing
- Removed lines (prefixed with -): Functionality that may no longer exist
- Context lines (no prefix): Unchanged code for better understanding

When to use: Use this for every file modified in the PR to identify what specific functionality needs testing.

Format your arguments as JSON:
{"file_path": "path relative to the repo root"}

Example: {"file_path": "src/services/user_service.py"}

How to read the diff:
- Lines with `+++`: Added code (new functionality to test)
- Lines with `---`: Removed code (check for regressions)
- Headers like `@@ -5,8 +5,9 @@`: Show where in the file changes occur

## Tool_7: list_directory_contents

Use this tool to explore the directory structure of the project, similar to the Linux `ls` command. This tool helps you understand the project layout and locate relevant files for testing.

This tool returns:
- List of files and subdirectories in the specified path
- File/directory metadata (name, path, type if available)
- Overview of the project structure

When to use: Use this tool when you need to:
- Explore the overall project structure before diving into specific files
- Find test directories and understand testing conventions
- Locate configuration files, documentation, or related modules
- Get an overview of a specific directory's contents before using other search tools

Format your arguments as JSON:
{"directory_path": "the path to the directory you want to list"}

Examples:
- List root directory: {"directory_path": "./path/to/project"}
- List source directory: {"directory_path": "./path/to/source"}
- List test directory: {"directory_path": "./path/to/tests"}

TIP: Use this tool first to get familiar with the project structure, then use Tool_4 (search_files_path_by_pattern) for more targeted file searches or Tool_5 (view_file_contents) to examine specific files you discover.

# Tree of Thought Format

Instead of proposing a single thought and action at a time, you will generate multiple thought-action pairs that represent different possible approaches to understanding the PR. This allows for exploring multiple branches of investigation simultaneously.

For each step, you must provide 3-5 different thought-action pairs, each with a unique ID.

You MUST follow this EXACT format:

```
### Exploration Step [Step Number]

#### Thought-Action Pair [ID]
- **Thought**: [Your reasoning about which tool to use and why]
- **Action**:
```[Exact tool name]
{
    [JSON parameters according to the required schema]
}
```
- **Expected Information**: [Brief description of what you expect to learn from this action]

#### Thought-Action Pair [ID]
[Format repeated for each additional pair]
```

Example of the CORRECT format:

```
### Exploration Step 1

#### Thought-Action Pair TA001
- **Thought**: I need to first understand what files were changed in this PR to identify the scope of testing needed.
- **Action**:
```search_files_path_by_pattern
{
    "pattern": "*/src/*.py"
}
```
- **Expected Information**: This will help me identify all Python source files that might have been modified in this PR.

#### Thought-Action Pair TA002
- **Thought**: I should look at the UserAuthentication class since it might be related to the PR changes based on the PR description.
- **Action**:
```search_class_in_project
{
    "class_name": "UserAuthentication"
}
```
- **Expected Information**: Details about the authentication system that may be affected by the changes.

#### Thought-Action Pair TA003
- **Thought**: I should examine the recent code changes directly to understand what's being modified.
- **Action**:
```view_code_changes
{
    "file_path": "src/auth/authentication.py"
}
```
- **Expected Information**: The exact code changes in the authentication module, which will be crucial for test planning.
```

After you've generated multiple thought-action pairs, I will select which ones to pursue. You should then generate a new set of thought-action pairs based on the information received.

IMPORTANT RULES:
- ALWAYS wrap the tool name and parameters in code blocks with three backticks!!!
- DO NOT repeat or summarize previous exploration steps - I already have this information
- Use the information gathered from previous steps to inform your new thought-action pairs
- Number your exploration steps sequentially (e.g., if the last step was "Exploration Step 2", the next one should be "Exploration Step 3")
- Maintain the same structured format for all thought-action pairs
- Each thought-action pair must have a unique ID (use format TA001, TA002, etc.)
- NEVER modify the tool names
- ALWAYS use valid JSON for parameters (double quotes for keys and string values)
- NEVER include explanations inside the Action code block
- Make sure each thought-action pair explores a different aspect of the PR

After receiving the results from the human, you should provide your next thought and action. Continue this process until you have gathered enough information to create a comprehensive test plan.

There are two situations in which you can begin to write a TEST PLAN:
1. when you believe you have gathered enough information to complete the test plan
2. when you receive a clear prompt to begin generating the test plan.

Please provide your conclusions in the following format:

### Thought: I have gathered enough information to create a comprehensive test plan for this PR.

### Test Plan Details:
```
# Test Plan for PR: [PR Title/Number]

## 1. Purpose
[Briefly explain the purpose of this test plan - what functionality is being tested and why]

## 2. Scope
[Define what is in scope and out of scope for this test plan, based on the PR changes]

## 3. Test Environment
[Specify required environment setup, configurations, dependencies, and prerequisites needed]

## 4. Test Cases
[Organize test cases by component or feature. For each test case, include:
- Test case ID/name
- Test objective
- Preconditions
- Test steps (numbered, clear instructions)
- Expected results
- Priority (High/Medium/Low)]
```

# TIPS:
- Focus on the CHANGED code first - that's what needs the most testing
- Prioritize tests based on risk and complexity of changes
- Include both positive test cases (expected behavior) and negative test cases (error handling)
- Your test plan should be specific enough for any tester to follow without requiring additional information
- Strive for accuracy, clarity, and completeness in your test plan
- Focus your test plan on the changed code sections, giving special attention to complex logic changes, new edge cases, and modified API interfaces.
"""

RELEVANCE_EVALUATION_PROMPT = f"""
As an expert software test plan evaluator, you need to assess the relevance of each thought-action pair and its observation to the pull request (PR). Evaluate how valuable this information is for creating a comprehensive test plan.

## Pull Request Information
### PR Content:
{{PR_Content}}

### Changed Files:
{{PR_Changed_Files}}

## Thought-Action Pair to Evaluate
### Thought:
{{Thought}}

### Action:
Tool: {{Action_Name}}
Parameters: {{Action_Parameters}}

### Observation (Tool Result):
{{Action_Observation}}

## Your Task
Score this thought-action pair on a scale of 1-10 based on its relevance to understanding the PR and creating an effective test plan.

Scoring criteria:
- 10: Extremely relevant - Provides critical information directly related to the core changes in the PR
- 8-9: Highly relevant - Offers important insights that will significantly improve the test plan
- 6-7: Moderately relevant - Contains useful information but not central to the PR changes
- 4-5: Somewhat relevant - Has some connection to the PR but is not a priority for testing
- 2-3: Minimally relevant - Only tangentially related to the PR
- 1: Not relevant - Provides no useful information for creating a test plan for this PR

Please provide:
1. A numerical score (1-10)
2. A brief justification (2-3 sentences) explaining your score

Format your response exactly as follows:
```
Relevance Score: [Your numerical score]
Justification: [Your brief explanation]
```

Focus only on how relevant this information is for testing the specific changes in this PR. Higher scores should be given to information that directly addresses the core functionality being modified.
"""
PR_TEST_PLAN_EDIT_PROMPT = f"""
Now that we have explored the codebase and gathered relevant information about the PR changes, please synthesize this knowledge to create a comprehensive test plan.

## PR Title and Description:
{{PR_Content}}

## Summaries of the changed functions/classes in the current PR:
{{summaries}}

Based on the information collected, please

1. Analyze PR descriptions, changed documents and tool observations to understand the purpose and scope of the changes.

2. Create a structured test plan that includes:
   - Purpose: What is being tested and why
   - Scope: What specific functionality is covered and what is excluded
   - Test Environment: Required setup and configurations
   - Test Cases: Detailed test steps with expected results
   - Special Considerations: Any edge cases, risks, or dependencies

3. Focus on testing:
   - New functionality introduced by the PR
   - Modified components and their interactions
   - Potential regression issues
   - Edge cases and error handling

4. Prioritize test cases based on:
   - Risk level (critical path functionality)
   - Complexity of changes
   - Customer impact

# TIPS:
- Focus on the CHANGED code first - that's what needs the most testing
- Prioritize tests based on risk and complexity of changes
- Include both positive test cases (expected behavior) and negative test cases (error handling)
- Your test plan should be specific enough for any tester to follow without requiring additional information
- Strive for accuracy, clarity, and completeness in your test plan
"""

PR_TEST_PLAN_CORRECT_PROMPT = f"""
Please help me create a comprehensive test plan for this pull request (PR) using a Tree of Thought approach. The test plan should follow IEEE software testing standards and include purpose, scope, environment, test cases, and expected results.

## PR Information

### Project Root Directory:
{{PR_Project_Root_Dir}}

### PR Title and Description:
{{PR_Content}}

### Changed Files Summary:
{{summaries}}

## NOTE:
{{notion}}

## Your Task

As a software test manager, please:

1. Analyze the PR description, changed files, and the previously collected information above to understand the purpose and scope of the changes.

2. For each exploration step, propose 3-5 different thought-action pairs that represent different approaches to understanding this PR. Each pair should include:
   - A thought explaining your reasoning
   - A specific tool action to gather information
   - What you expect to learn from this action

   IMPORTANT: Do not propose actions to gather information that has already been collected in previous steps as listed above.

3. I will select which thought-action pairs to pursue for each exploration step, and we'll continue this process until we have enough information.

Your final test plan should be thorough yet concise, and clear enough that any QA engineer could execute it without additional information.

"""