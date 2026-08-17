"""
RAG Knowledge Base for Corporate Information.

Provides grounded answers based on approved corporate data:
- Company information
- Departments and teams
- Office policies
- Visitor instructions
- FAQs
- Course/internship/vacancy information

Architecture:
- Knowledge is loaded from YAML/JSON files in a configurable directory
- Each knowledge entry has: title, content, category, source
- Simple keyword/semantic search finds relevant entries
- Found entries are injected into the prompt context
- AI responses based on knowledge include source attribution

The AI MUST NOT invent information not present in the knowledge base.
If no relevant knowledge is found, the AI says "I don't have that information."
"""

import os
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path
import structlog

logger = structlog.get_logger()

# Default knowledge directory
KNOWLEDGE_DIR = os.environ.get("KNOWLEDGE_DIR", "./knowledge")


@dataclass
class KnowledgeEntry:
    """A single piece of corporate knowledge."""
    id: str
    title: str
    content: str
    category: str
    keywords: List[str] = field(default_factory=list)
    source: str = "corporate_knowledge_base"
    priority: int = 0  # Higher = more important


@dataclass
class SearchResult:
    """Result from knowledge search."""
    entries: List[KnowledgeEntry]
    query: str
    total_found: int


class KnowledgeBase:
    """
    Corporate knowledge base for grounding AI responses.
    
    Loads knowledge from JSON files and provides search functionality.
    Search is keyword-based (suitable for small-to-medium knowledge sets).
    For larger deployments, upgrade to vector search (e.g., Bedrock Knowledge Bases).
    """

    def __init__(self, knowledge_dir: str = KNOWLEDGE_DIR):
        self.knowledge_dir = knowledge_dir
        self._entries: List[KnowledgeEntry] = []
        self._loaded = False

    async def initialize(self) -> None:
        """Load all knowledge entries from the knowledge directory."""
        self._entries = []

        knowledge_path = Path(self.knowledge_dir)
        if not knowledge_path.exists():
            # Create directory with default knowledge
            knowledge_path.mkdir(parents=True, exist_ok=True)
            self._create_default_knowledge(knowledge_path)
            logger.info("Created default knowledge directory", path=str(knowledge_path))

        # Load all .json files
        for json_file in knowledge_path.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if isinstance(data, list):
                    for item in data:
                        entry = self._parse_entry(item)
                        if entry:
                            self._entries.append(entry)
                elif isinstance(data, dict) and "entries" in data:
                    for item in data["entries"]:
                        entry = self._parse_entry(item)
                        if entry:
                            self._entries.append(entry)

            except Exception as e:
                logger.error("Failed to load knowledge file", file=str(json_file), error=str(e))

        self._loaded = True
        logger.info("Knowledge base loaded", entries=len(self._entries), dir=str(knowledge_path))

    def search(self, query: str, max_results: int = 3, category: Optional[str] = None) -> SearchResult:
        """
        Search knowledge base by keyword matching.
        
        Args:
            query: Search query (visitor's question)
            max_results: Maximum entries to return
            category: Optional category filter
            
        Returns:
            SearchResult with relevant entries
        """
        if not self._loaded or not self._entries:
            return SearchResult(entries=[], query=query, total_found=0)

        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored_entries = []
        for entry in self._entries:
            # Category filter
            if category and entry.category.lower() != category.lower():
                continue

            # Score based on keyword matches
            score = 0

            # Check title
            if any(word in entry.title.lower() for word in query_words):
                score += 3

            # Check keywords
            for keyword in entry.keywords:
                if keyword.lower() in query_lower:
                    score += 2

            # Check content (partial)
            content_lower = entry.content.lower()
            for word in query_words:
                if len(word) > 3 and word in content_lower:
                    score += 1

            # Priority boost
            score += entry.priority * 0.5

            if score > 0:
                scored_entries.append((score, entry))

        # Sort by score descending
        scored_entries.sort(key=lambda x: x[0], reverse=True)

        results = [entry for _, entry in scored_entries[:max_results]]
        return SearchResult(entries=results, query=query, total_found=len(scored_entries))

    def format_context(self, results: SearchResult) -> Optional[str]:
        """
        Format search results as context for the AI prompt.
        
        Returns:
            Formatted string to inject into prompt, or None if no results.
        """
        if not results.entries:
            return None

        lines = ["--- CORPORATE KNOWLEDGE (use ONLY this information to answer) ---"]
        for entry in results.entries:
            lines.append(f"\n[{entry.category}] {entry.title}")
            lines.append(entry.content)
            lines.append(f"(Source: {entry.source})")

        lines.append("\n--- END KNOWLEDGE ---")
        lines.append("IMPORTANT: Only use the information above. If the answer is not in the knowledge base, say 'I don't have that specific information, but I can help you find the right person to ask.'")

        return "\n".join(lines)

    def get_categories(self) -> List[str]:
        """Get all available knowledge categories."""
        return list(set(entry.category for entry in self._entries))

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @staticmethod
    def _parse_entry(data: dict) -> Optional[KnowledgeEntry]:
        """Parse a dict into a KnowledgeEntry."""
        if not data.get("title") or not data.get("content"):
            return None
        return KnowledgeEntry(
            id=data.get("id", ""),
            title=data["title"],
            content=data["content"],
            category=data.get("category", "general"),
            keywords=data.get("keywords", []),
            source=data.get("source", "corporate_knowledge_base"),
            priority=data.get("priority", 0),
        )

    @staticmethod
    def _create_default_knowledge(path: Path) -> None:
        """Create a default knowledge file with Code Origin.AI info."""
        default_entries = [
            {
                "id": "company_about",
                "title": "About Code Origin.AI",
                "content": "Code Origin.AI is a technology company specializing in AI and software development. We are located in India and focus on building intelligent solutions.",
                "category": "company",
                "keywords": ["about", "company", "code origin", "what do you do"],
                "priority": 2
            },
            {
                "id": "office_hours",
                "title": "Office Hours",
                "content": "Our office hours are Monday to Friday, 9:00 AM to 6:00 PM IST. The office is closed on weekends and national holidays.",
                "category": "policy",
                "keywords": ["hours", "timing", "open", "closed", "when", "schedule"],
                "priority": 1
            },
            {
                "id": "visitor_wifi",
                "title": "Visitor WiFi",
                "content": "Visitors can connect to the 'CodeOrigin-Guest' WiFi network. Please ask the receptionist for the current password.",
                "category": "visitor_info",
                "keywords": ["wifi", "internet", "network", "password", "connect"],
                "priority": 1
            },
            {
                "id": "visitor_policy",
                "title": "Visitor Policy",
                "content": "All visitors must check in at reception. Visitors are required to wear a visitor badge while on premises. Please return the badge when leaving.",
                "category": "policy",
                "keywords": ["visitor", "badge", "policy", "rules", "check in"],
                "priority": 2
            },
            {
                "id": "departments",
                "title": "Departments",
                "content": "Code Origin.AI has the following departments: Engineering, Management, HR (Human Resources), Sales, and Marketing. Each department is led by a department head.",
                "category": "company",
                "keywords": ["department", "team", "engineering", "hr", "sales", "management"],
                "priority": 1
            },
            {
                "id": "parking",
                "title": "Parking Information",
                "content": "Visitor parking is available in the basement level B1. Please take a parking ticket from the machine and get it validated at reception before leaving.",
                "category": "visitor_info",
                "keywords": ["parking", "car", "vehicle", "basement", "where to park"],
                "priority": 1
            },
            {
                "id": "emergency",
                "title": "Emergency Procedures",
                "content": "In case of emergency, proceed to the nearest exit. Assembly point is in the front parking area. Do not use elevators during emergencies. Emergency contact: security desk at extension 100.",
                "category": "safety",
                "keywords": ["emergency", "fire", "exit", "evacuation", "safety"],
                "priority": 3
            },
        ]

        with open(path / "default_knowledge.json", 'w', encoding='utf-8') as f:
            json.dump({"entries": default_entries}, f, indent=2, ensure_ascii=False)


# Global singleton
knowledge_base = KnowledgeBase()
