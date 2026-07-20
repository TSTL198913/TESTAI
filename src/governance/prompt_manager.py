# src/governance/prompt_manager.py
import os

import yaml


class PromptManager:
    def __init__(self, prompts_dir="prompts"):
        self.prompts_dir = prompts_dir
        self.templates = {}
        self._load_all_prompts()

    def _load_all_prompts(self):
        import logging

        logger = logging.getLogger(__name__)
        if not os.path.exists(self.prompts_dir):
            logger.warning(f"Prompts directory not found: {self.prompts_dir}")
            return
        for filename in os.listdir(self.prompts_dir):
            if filename.endswith(".yaml"):
                filepath = os.path.join(self.prompts_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        if data:
                            self.templates.update(data)
                except (yaml.YAMLError, IOError) as e:
                    logger.error(f"Failed to load prompt file {filename}: {e}")

    def get(self, template_name, **kwargs):
        """获取 Prompt 并填充变量"""
        template = self.templates.get(template_name)
        if not template:
            raise ValueError(f"Prompt template {template_name} not found")
        return template.format(**kwargs)  # 支持 Python 字符串格式化注入
