import os
import yaml
from typing import Optional, Dict, List
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)

class Skill:
    name: str
    description: str
    trigger_phrases: List[str]
    steps: List[str]
    required_tools: List[str]

class SkillFactory:
    """Dynamic skill creation and discovery."""

    def __init__(self, skills_dir: str = "../ruflo-agent/skills"):
        self.skills_dir = Path(skills_dir)
        self.skills: Dict[str, Skill] = {}
        self._discover_skills()

    def _discover_skills(self) -> None:
        if not self.skills_dir.exists():
            logger.warning("Skills directory not found", path=self.skills_dir)
            return
        for skill_file in self.skills_dir.glob("*.skill"):
            try:
                with open(skill_file, "r") as f:
                    data = yaml.safe_load(f)
                    skill = Skill(**data)
                    self.skills[skill.name] = skill
            except Exception as e:
                logger.error("Failed to load skill", file=skill_file, error=str(e))
        logger.info("Skills discovered", count=len(self.skills))

    def create_skill_from_task(self, task_description: str, task_id: Optional[str] = None) -> Skill:
        """Create a new skill from a successfully completed task."""
        skill_name = task_id or task_description.lower().replace(" ", "_")[:30]
        skill = Skill(
            name=skill_name,
            description=task_description,
            trigger_phrases=[task_description.split()[0].lower()],
            steps=["execute task as completed"],
            required_tools=["tool_executor"]
        )
        self.skills[skill_name] = skill
        self._save_skill(skill)
        logger.info("Skill created", name=skill_name)
        return skill

    def _save_skill(self, skill: Skill) -> None:
        skill_path = self.skills_dir / f"{skill.name}.skill"
        with open(skill_path, "w") as f:
            yaml.dump(skill.__dict__, f, default_flow_style=False)

    def load_skill(self, skill_name: str) -> Optional[Skill]:
        return self.skills.get(skill_name)

    def list_skills(self) -> List[Dict]:
        return [s.__dict__ for s in self.skills.values()]