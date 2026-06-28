import os
import json
from pathlib import Path
import torch
import numpy as np
from transformers import T5EncoderModel, RobertaTokenizer
from tqdm import tqdm
from tree_sitter_languages import get_parser
import pandas as pd
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    RecursiveJsonSplitter,
    Language
)
from langchain_core.documents import Document
from tasks.BaseTask import BaseTask
from prompt.embedding.test_plan import EMBEDDING_TEST_PLAN_SYSTEM_PROMPT, EMBEDDING_TEST_PLAN_USER_PROMPT

class Embedding(BaseTask):
    """
    改进的嵌入策略，支持代码和文档的混合召回，并优化模型加载和内容缓存。
    对代码文件提取函数/类，对非代码文件进行chunk分割。
    """
    
    # 类级别的模型缓存
    _model_cache = {}
    _tokenizer_cache = {}
    
    # 类级别的内容和嵌入缓存
    _content_info_cache = {}
    _embeddings_cache = {}
    
    def __init__(self, config):
        """
        用提供的配置初始化嵌入任务。
        
        Args:
            config (dict): 任务的配置字典
        """
        super().__init__(config)
        self.model_name = "Salesforce/codet5p-110m-embedding"
        self.device = torch.device("cuda:3" if torch.cuda.is_available() else "cpu")
        
        # 使用缓存的模型和tokenizer
        self.tokenizer = None
        self.model = None
        self.embeddings = None  # 存储所有内容的嵌入（代码+文档）
        self.content_info = []  # 存储所有内容信息（代码+文档）
        
        # 配置参数
        self.code_chunk_size = 3000
        self.text_chunk_size = 1000
        
        # 支持的编程语言和文件扩展名映射
        self.code_extensions = {
            'python': ['py'],
            'javascript': ['js'],
            'typescript': ['ts'],
            'tsx': ['tsx'],
            'java': ['java'],
            'cpp': ['cpp', 'cc', 'cxx'],
            'c': ['c'],
            'csharp': ['cs'],
            'php': ['php'],
            'ruby': ['rb'],
            'go': ['go'],
            'rust': ['rs'],
            'swift': ['swift'],
            'kotlin': ['kt'],
            'scala': ['scala']
        }
        
        # 无效的文件扩展名（二进制文件等）
        self.invalid_extensions = [
            '.pyc', '.pyo', '.pyd', '.so', '.dll', '.dylib',
            '.class', '.jar', '.war', '.ear',
            '.exe', '.bin', '.obj', '.o',
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.ico',
            '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv',
            '.zip', '.tar', '.gz', '.rar', '.7z',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.db', '.sqlite', '.sqlite3'
        ]
        
        # 初始化解析器
        self.parsers = {}
        for lang in ['python', 'javascript', 'typescript', 'tsx']:
            try:
                self.parsers[lang] = get_parser(lang)
            except:
                print(f"Warning: Could not load parser for {lang}")
        
        # 项目目录和缓存键
        self.project_dir = self.config['CKG']['project_dir']
        self.content_structure_file = os.path.join(self.project_dir, "content_structure.json")
        self.project_cache_key = self.get_project_cache_key()
        
        # 加载或分析项目内容（使用缓存）
        self.load_or_analyze_project()
    
    def get_project_cache_key(self):
        """
        生成项目的缓存键，基于项目路径和配置
        """
        project_path = os.path.abspath(self.project_dir)
        cache_key = f"{project_path}_{self.code_chunk_size}_{self.text_chunk_size}"
        return cache_key
    
    @classmethod
    def get_model_cache_key(cls, model_name, device):
        """生成模型缓存的键"""
        return f"{model_name}_{device}"
    
    @classmethod
    def clear_all_cache(cls):
        """清空所有缓存（用于内存管理）"""
        cls._model_cache.clear()
        cls._tokenizer_cache.clear()
        cls._content_info_cache.clear()
        cls._embeddings_cache.clear()
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("All caches cleared")
    
    @classmethod
    def get_cache_info(cls):
        """获取缓存信息"""
        return {
            "model_cache_count": len(cls._model_cache),
            "content_cache_count": len(cls._content_info_cache),
            "embeddings_cache_count": len(cls._embeddings_cache),
            "cached_projects": list(cls._content_info_cache.keys()),
            "cached_models": list(cls._model_cache.keys())
        }
    
    def load_or_analyze_project(self):
        """
        加载或分析项目内容，使用缓存机制
        """
        # 检查内容信息缓存
        if self.project_cache_key in self._content_info_cache:
            print(f"Loading content_info from cache for project: {self.project_dir}")
            self.content_info = self._content_info_cache[self.project_cache_key]
            print(f"Loaded {len(self.content_info)} content items from cache")
            return
        
        # 缓存中没有，检查是否需要重新分析项目
        check_timestamps = self.config.get('Embedding', {}).get('check_file_timestamps', False)
        
        if self.should_reanalyze_project(check_timestamps=check_timestamps):
            print("Re-analyzing project...")
            self.analyze_project(self.project_dir)
        else:
            print("Loading existing content structure from file...")
            self.load_content_structure()
        
        # 将分析结果存入缓存
        if self.content_info:
            self._content_info_cache[self.project_cache_key] = self.content_info
            print(f"Cached content_info for project: {self.project_dir}")
    
    def load_models(self):
        """加载CodeT5+模型和tokenizer，使用缓存机制"""
        cache_key = self.get_model_cache_key(self.model_name, self.device)
        
        print(f"Using device: {self.device}")
        
        # 检查tokenizer缓存
        if cache_key in self._tokenizer_cache:
            print("Loading tokenizer from cache...")
            self.tokenizer = self._tokenizer_cache[cache_key]
        else:
            print("Loading tokenizer from disk...")
            self.tokenizer = RobertaTokenizer.from_pretrained(self.model_name)
            self._tokenizer_cache[cache_key] = self.tokenizer
        
        # 检查模型缓存
        if cache_key in self._model_cache:
            print("Loading model from cache...")
            self.model = self._model_cache[cache_key]
        else:
            print("Loading model from disk...")
            self.model = T5EncoderModel.from_pretrained(self.model_name).to(self.device)
            self.model.eval()
            self._model_cache[cache_key] = self.model
        
        print("Models loaded successfully")
    
    def get_embeddings_cache_key(self):
        """
        生成嵌入向量的缓存键，基于项目内容和模型
        """
        model_key = self.get_model_cache_key(self.model_name, self.device)
        return f"{self.project_cache_key}_{model_key}"
    
    def load_or_compute_embeddings(self):
        """
        加载或计算嵌入向量，使用缓存机制
        """
        embeddings_cache_key = self.get_embeddings_cache_key()
        
        # 检查嵌入向量缓存
        if embeddings_cache_key in self._embeddings_cache:
            print("Loading embeddings from cache...")
            self.embeddings = self._embeddings_cache[embeddings_cache_key]
            print(f"Loaded embeddings with shape: {self.embeddings.shape}")
            return True
        
        # 缓存中没有，尝试从文件加载
        embeddings_loaded = False
        if os.path.exists(self.config['Embedding']['load_embedding']):
            embeddings_loaded = self.load_embeddings(
                self.config['Embedding']['load_embedding'],
                self.config['Embedding']['info_file']
            )
        
        if not embeddings_loaded:
            print("Computing new embeddings...")
            self.compute_all_embeddings()
            self.save_embeddings(
                self.config['Embedding']['load_embedding'],
                self.config['Embedding']['info_file']
            )
        
        # 将嵌入向量存入缓存
        if self.embeddings is not None:
            self._embeddings_cache[embeddings_cache_key] = self.embeddings
            print(f"Cached embeddings for key: {embeddings_cache_key}")
        
        return True
    
    def should_reanalyze_project(self, check_timestamps=False):
        """
        检查是否需要重新分析项目
        基于以下条件：
        1. content_structure.json 文件不存在
        2. content_structure.json 文件为空或格式错误
        3. 项目文件有更新（可选：基于修改时间）
        
        Args:
            check_timestamps (bool): 是否检查文件修改时间
        """
        # 检查文件是否存在
        if not os.path.exists(self.content_structure_file):
            print("Content structure file not found, need to analyze project")
            return True
        
        # 检查文件是否有效
        try:
            with open(self.content_structure_file, 'r', encoding='utf-8') as f:
                content_data = json.load(f)
            
            # 检查是否为空或无效格式
            if not content_data or not isinstance(content_data, list):
                print("Content structure file is empty or invalid, need to re-analyze")
                return True
            
            # 检查是否有内容项
            if len(content_data) == 0:
                print("No content items found in structure file, need to re-analyze")
                return True
            
            print(f"Found {len(content_data)} existing content items in file")
            return False
            
        except (json.JSONDecodeError, Exception) as e:
            print(f"Error reading content structure file: {e}, need to re-analyze")
            return True
    
    def load_content_structure(self):
        """从现有的 content_structure.json 文件加载内容结构"""
        try:
            with open(self.content_structure_file, 'r', encoding='utf-8') as f:
                self.content_info = json.load(f)
            print(f"Loaded {len(self.content_info)} content items from file")
        except Exception as e:
            print(f"Error loading content structure: {e}")
            # 如果加载失败，重新分析
            print("Falling back to re-analyzing project...")
            self.analyze_project(self.project_dir)
    
    def is_code_file(self, filename):
        """判断文件是否为代码文件"""
        ext = Path(filename).suffix.lower().lstrip('.')
        for lang, exts in self.code_extensions.items():
            if ext in exts:
                return True, lang
        return False, None
    
    def is_invalid_file(self, filename):
        """判断文件是否应该被忽略"""
        filename_lower = filename.lower()
        for invalid_ext in self.invalid_extensions:
            if filename_lower.endswith(invalid_ext):
                return True
        return False
    
    def read_file_content(self, file_path):
        """安全地读取文件内容"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
                    print(f"Warning: Used latin-1 encoding for {file_path}")
                    return content
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
                return ""
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return ""
    
    def extract_code_definitions(self, node, content, file_path, lang):
        """从代码文件中提取函数和类定义"""
        items = []
        
        def get_node_text(node):
            return content[node.start_byte:node.end_byte].decode('utf8')
        
        # 根据不同语言处理不同的节点类型
        if lang in ['tsx', 'typescript', 'javascript']:
            if node.type in ['function_declaration', 'method_definition', 'arrow_function']:
                name = self.extract_function_name(node, lang)
                if name:
                    items.append({
                        'type': 'code',
                        'content_type': 'function',
                        'name': name,
                        'content': get_node_text(node),
                        'file': os.path.relpath(file_path, self.config['CKG']['project_dir']),
                        'language': lang
                    })
            elif node.type == 'class_declaration':
                name = self.extract_class_name(node, lang)
                if name:
                    items.append({
                        'type': 'code',
                        'content_type': 'class',
                        'name': name,
                        'content': get_node_text(node),
                        'file': os.path.relpath(file_path, self.config['CKG']['project_dir']),
                        'language': lang
                    })
        
        elif lang == 'python':
            if node.type == 'function_definition':
                name = self.extract_function_name(node, lang)
                if name:
                    items.append({
                        'type': 'code',
                        'content_type': 'function',
                        'name': name,
                        'content': get_node_text(node),
                        'file': os.path.relpath(file_path, self.config['CKG']['project_dir']),
                        'language': lang
                    })
            elif node.type == 'class_definition':
                name = self.extract_class_name(node, lang)
                if name:
                    items.append({
                        'type': 'code',
                        'content_type': 'class',
                        'name': name,
                        'content': get_node_text(node),
                        'file': os.path.relpath(file_path, self.config['CKG']['project_dir']),
                        'language': lang
                    })
        
        # 递归处理子节点
        for child in node.children:
            items.extend(self.extract_code_definitions(child, content, file_path, lang))
        
        return items
    
    def extract_function_name(self, node, lang):
        """提取函数名"""
        for child in node.children:
            if child.type == 'identifier':
                return child.text.decode('utf8')
        return None
    
    def extract_class_name(self, node, lang):
        """提取类名"""
        for child in node.children:
            if child.type == 'identifier':
                return child.text.decode('utf8')
        return None
    
    def split_document_content(self, content, file_path, lang=None):
        """将文档内容分割成chunks"""
        chunks = []
        
        try:
            if file_path.endswith('.json'):
                splitter = RecursiveJsonSplitter(max_chunk_size=self.text_chunk_size)
                try:
                    content_dict = json.loads(content)
                    doc_chunks = splitter.create_documents([content_dict], convert_lists=True)
                except:
                    # 如果JSON解析失败，当作普通文本处理
                    splitter = RecursiveCharacterTextSplitter(
                        chunk_size=self.text_chunk_size,
                        chunk_overlap=200,
                        length_function=len
                    )
                    doc_chunks = splitter.create_documents([content])
            else:
                # 普通文本文件
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=self.text_chunk_size,
                    chunk_overlap=200,
                    length_function=len
                )
                doc_chunks = splitter.create_documents([content])
            
            # 转换为我们需要的格式
            rel_file_path = os.path.relpath(file_path, self.config['CKG']['project_dir'])
            for i, chunk in enumerate(doc_chunks):
                chunks.append({
                    'type': 'document',
                    'content_type': 'chunk',
                    'name': f"{Path(file_path).name}_chunk_{i}",
                    'content': chunk.page_content,
                    'file': rel_file_path,
                    'language': 'text',
                    'chunk_index': i
                })
        
        except Exception as e:
            print(f"Error splitting document {file_path}: {e}")
        
        return chunks
    
    def analyze_project(self, project_dir):
        """分析整个项目，提取代码定义和文档chunks"""
        print(f"Analyzing project: {project_dir}")
        
        self.content_info = []
        
        # 遍历项目目录
        for root, dirs, files in os.walk(project_dir):
            # 忽略隐藏目录
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                file_path = os.path.join(root, file)
                
                # 跳过无效文件
                if self.is_invalid_file(file_path):
                    continue
                
                # 读取文件内容
                content = self.read_file_content(file_path)
                if not content.strip():
                    continue
                
                # 判断是否为代码文件
                is_code, lang = self.is_code_file(file_path)
                
                if is_code and lang in self.parsers:
                    # 处理代码文件 - 提取函数和类
                    try:
                        parser = self.parsers[lang]
                        tree = parser.parse(content.encode('utf8'))
                        items = self.extract_code_definitions(tree.root_node, content.encode('utf8'), file_path, lang)
                        self.content_info.extend(items)
                        print(f"Extracted {len(items)} code items from {file_path}")
                    except Exception as e:
                        print(f"Error parsing code file {file_path}: {e}")
                else:
                    # 处理非代码文件 - 分割为chunks
                    chunks = self.split_document_content(content, file_path, lang)
                    self.content_info.extend(chunks)
                    print(f"Split {len(chunks)} chunks from {file_path}")
        
        print(f"Total content items: {len(self.content_info)}")
        
        # 保存分析结果
        output_file = os.path.join(project_dir, "content_structure.json")
        self.save_content_structure(output_file)
    
    def save_content_structure(self, output_file):
        """保存内容结构到JSON文件"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.content_info, f, ensure_ascii=False, indent=2)
            print(f"Saved content structure to {output_file}")
        except Exception as e:
            print(f"Error saving content structure: {e}")
    
    def encode_text(self, text, max_length=512):
        """将文本转换为嵌入向量"""
        # 确保模型已加载
        if not self.model or not self.tokenizer:
            self.load_models()
            
        with torch.no_grad():
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                max_length=max_length,
                padding="max_length",
                truncation=True
            ).to(self.device)
            
            outputs = self.model(
                input_ids=inputs.input_ids,
                attention_mask=inputs.attention_mask
            )
            
            embedding = torch.mean(outputs.last_hidden_state, dim=1)
            return embedding
    
    def compute_all_embeddings(self, batch_size=128):
        """计算所有内容的嵌入向量"""
        # 确保模型已加载
        if not self.model or not self.tokenizer:
            self.load_models()
        
        print("Computing embeddings for all content...")
        
        all_embeddings = []
        
        for i in tqdm(range(0, len(self.content_info), batch_size)):
            batch = [item["content"] for item in self.content_info[i:i+batch_size]]
            
            with torch.no_grad():
                inputs = self.tokenizer(
                    batch,
                    return_tensors="pt",
                    max_length=512,
                    padding="max_length",
                    truncation=True
                ).to(self.device)
                
                outputs = self.model(
                    input_ids=inputs.input_ids,
                    attention_mask=inputs.attention_mask
                )
                
                batch_embeddings = torch.mean(outputs.last_hidden_state, dim=1)
                all_embeddings.append(batch_embeddings.cpu())
        
        if all_embeddings:
            self.embeddings = torch.cat(all_embeddings, dim=0)
            self.embeddings = torch.nn.functional.normalize(self.embeddings, p=2, dim=1)
            print(f"Computed embeddings with shape: {self.embeddings.shape}")

    def save_top_index(self, top_indexes, file_path):
        """保存top_index到文件"""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w') as f:
            for index in top_indexes:
                f.write(f"{index}\n")
        print(f"Saved top_index to {file_path}")

    def save_similarity_scores(self, similarity_scores, file_path):
        """保存相似性得分到文件"""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w') as f:
            for score in similarity_scores:
                f.write(f"{score}\n")
        print(f"Saved similarity_scores to {file_path}")

    def save_pr_result(self, results):
        """保存结果到文件"""
        os.makedirs(os.path.dirname(self.config['Embedding']['result_path']), exist_ok=True)
        with open(self.config['Embedding']['result_path'], 'w') as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        print(f"Saved result to {self.config['Embedding']['result_path']}")

    def find_similar_content(self, query_texts, top_k=20):
        """
        使用组合查询找到相似内容
        
        Args:
            query_texts (list): 查询文本列表 [PR_Content, PR_Changed_Files]
            top_k (int): 返回的相似内容数量
            
        Returns:
            list: 相似内容列表
        """
        if self.embeddings is None:
            print("No embeddings available. Please compute embeddings first.")
            return []
        
        print(f"Finding top {top_k} similar content for combined query...")
        
        # 如果result_path存在，则直接加载
        if os.path.exists(self.config['Embedding']['result_path']):
            with open(self.config['Embedding']['result_path'], 'r') as f:
                results = json.load(f)
            print(f"Loaded result from {self.config['Embedding']['result_path']}")
            return results

        # 计算组合查询的嵌入
        combined_query = " ".join(query_texts)
        query_embedding = self.encode_text(combined_query)
        query_embedding = torch.nn.functional.normalize(query_embedding, p=2, dim=1)
        
        # 计算相似性得分
        self.embeddings = self.embeddings.to(self.device)
        similarity_scores = torch.mm(query_embedding, self.embeddings.t()).squeeze(0)
        
        # 获取top_k相似项
        if len(similarity_scores.shape) == 0:
            similarity_scores = similarity_scores.unsqueeze(0)
        top_indices = torch.argsort(similarity_scores, descending=True)[:top_k].cpu().numpy()

        # 准备结果
        results = []
        for idx in top_indices:
            info = self.content_info[idx]
            score = similarity_scores[idx].item()
            
            result = {
                "type": info["type"],
                "content_type": info["content_type"],
                "name": info["name"],
                "file": info["file"],
                "content": info["content"],
                "language": info.get("language", ""),
                "similarity_score": score
            }
            
            # 如果是文档chunk，添加chunk信息
            if info["type"] == "document":
                result["chunk_index"] = info.get("chunk_index", 0)
            
            results.append(result)
        
        self.save_pr_result(results)
        return results
    
    def format_mixed_results(self, results):
        """格式化混合内容结果供LLM使用"""
        formatted_results = ""
        
        code_count = 0
        doc_count = 0
        
        for i, result in enumerate(results):
            if result["type"] == "code":
                code_count += 1
                formatted_results += f"### Code Block {code_count}\n"
                formatted_results += f"- **Type**: {result['type']} ({result['content_type']})\n"
                formatted_results += f"- **Name**: {result['name']}\n"
                formatted_results += f"- **File**: {result['file']}\n"
                formatted_results += f"- **Language**: {result['language']}\n"
                formatted_results += f"- **Similarity Score**: {result['similarity_score']:.4f}\n"
                formatted_results += f"- **Code**:\n```{result['language']}\n{result['content']}\n```\n\n"
                
            else:  # document
                doc_count += 1
                formatted_results += f"### Document Chunk {doc_count}\n"
                formatted_results += f"- **Type**: {result['type']} ({result['content_type']})\n"
                formatted_results += f"- **Name**: {result['name']}\n"
                formatted_results += f"- **File**: {result['file']}\n"
                formatted_results += f"- **Chunk Index**: {result.get('chunk_index', 0)}\n"
                formatted_results += f"- **Similarity Score**: {result['similarity_score']:.4f}\n"
                formatted_results += f"- **Content**:\n```\n{result['content']}\n```\n\n"
        
        return formatted_results
    
    def save_embeddings(self, embeddings_file, info_file=None):
        """保存嵌入向量和内容信息"""
        if self.embeddings is None:
            print("No embeddings to save.")
            return
        
        print(f"Saving embeddings to {embeddings_file}...")
        torch.save(self.embeddings, embeddings_file)
        
        if info_file:
            print(f"Saving content info to {info_file}...")
            with open(info_file, 'w', encoding='utf-8') as f:
                json.dump(self.content_info, f, ensure_ascii=False, indent=2)
    
    def load_embeddings(self, embeddings_file, info_file=None):
        """加载嵌入向量和内容信息"""
        print(f"Loading embeddings from {embeddings_file}...")
        try:
            self.embeddings = torch.load(embeddings_file, map_location=self.device)
            print(f"Loaded embeddings with shape: {self.embeddings.shape}")
            
            if info_file and os.path.exists(info_file):
                print(f"Loading content info from {info_file}...")
                with open(info_file, 'r', encoding='utf-8') as f:
                    self.content_info = json.load(f)
                print(f"Loaded info for {len(self.content_info)} content items.")
            
            return True
        except Exception as e:
            print(f"Error loading embeddings: {e}")
            return False

    def run(self):
        """运行改进的嵌入任务生成测试计划"""
        # 确保模型已加载
        if not self.model or not self.tokenizer:
            self.load_models()
        
        # 加载或计算嵌入（使用缓存）
        self.load_or_compute_embeddings()
        
        # 使用组合查询进行相似性搜索
        print("Finding similar content using combined query...")
        query_texts = [self.PR_Content, self.PR_Changed_Files]

        similar_content = self.find_similar_content(query_texts, top_k=10)
        
        return None
        # 格式化结果
        formatted_results = self.format_mixed_results(similar_content)
        
        # 创建测试计划生成的提示
        user_prompt = EMBEDDING_TEST_PLAN_USER_PROMPT.format(
            PR_Content=self.PR_Content,
            summaries=self.PR_Changed_Files,
            Similar_Code=formatted_results
        )
        
        # 生成测试计划
        print("Generating test plan...")
        messages = [
            {"role": "system", "content": EMBEDDING_TEST_PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
        test_plan, truncated = self.llm(messages, self.config['Agent']['llm_model'])
        
        # 保存轨迹
        trajectory = {
            'system_prompt': EMBEDDING_TEST_PLAN_SYSTEM_PROMPT,
            'user_prompt': user_prompt,
            'react_info': [],
            'error_content': "",
            'if_truncated': truncated
        }
        
        if '4. Test Cases' in test_plan:
            react_info = {
                'thought': "",
                'test_plan': test_plan
            }
            trajectory['react_info'].append(react_info)
            self.save_result(trajectory)
            return test_plan
        else:
            return None