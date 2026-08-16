"""
Database operations for visitors/persons.
Handles CRUD and face embedding vector search.
"""

import uuid
from datetime import datetime
from typing import Optional, List, Tuple

import numpy as np
from sqlalchemy import select, update, func, text
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from database.models import Person, Visit, Conversation, ConversationMessage

logger = structlog.get_logger()


class VisitorRepository:
    """Repository pattern for visitor database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_person(
        self,
        name: str,
        face_embedding: Optional[np.ndarray] = None,
        image_path: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        company: Optional[str] = None,
        role: Optional[str] = None,
        consent_status: str = "pending"
    ) -> Person:
        """Create a new person record."""
        person = Person(
            person_id=uuid.uuid4(),
            name=name,
            email=email,
            phone=phone,
            company=company,
            role=role,
            image_path=image_path,
            face_embedding=face_embedding.tolist() if face_embedding is not None else None,
            consent_status=consent_status,
            last_seen=datetime.utcnow(),
            visit_count=1
        )
        self.db.add(person)
        await self.db.flush()
        logger.info("Created new person", person_id=str(person.person_id), name=name)
        return person

    async def get_person_by_id(self, person_id: uuid.UUID) -> Optional[Person]:
        """Get a person by their ID."""
        result = await self.db.execute(
            select(Person).where(Person.person_id == person_id)
        )
        return result.scalar_one_or_none()

    async def search_by_face(
        self,
        embedding: np.ndarray,
        threshold: float = 0.6,
        limit: int = 5
    ) -> List[Tuple[Person, float]]:
        """
        Search for a person by face embedding using cosine similarity.
        Returns list of (person, similarity_score) tuples.
        """
        embedding_list = embedding.tolist()

        # Use pgvector cosine distance (1 - cosine_similarity)
        query = text("""
            SELECT person_id, name, email, phone, company, role,
                   image_path, consent_status, last_seen, visit_count,
                   1 - (face_embedding <=> :embedding::vector) AS similarity
            FROM persons
            WHERE face_embedding IS NOT NULL
              AND consent_status = 'granted'
            ORDER BY face_embedding <=> :embedding::vector
            LIMIT :limit
        """)

        result = await self.db.execute(
            query,
            {"embedding": str(embedding_list), "limit": limit}
        )
        rows = result.fetchall()

        matches = []
        for row in rows:
            similarity = row.similarity
            if similarity >= threshold:
                person = await self.get_person_by_id(row.person_id)
                if person:
                    matches.append((person, similarity))

        logger.info(
            "Face search completed",
            matches_found=len(matches),
            threshold=threshold
        )
        return matches

    async def update_last_seen(self, person_id: uuid.UUID) -> None:
        """Update the last_seen timestamp and increment visit count."""
        await self.db.execute(
            update(Person)
            .where(Person.person_id == person_id)
            .values(
                last_seen=datetime.utcnow(),
                visit_count=Person.visit_count + 1
            )
        )

    async def create_visit(
        self,
        person_id: uuid.UUID,
        employee_to_meet: Optional[uuid.UUID] = None,
        purpose: Optional[str] = None
    ) -> Visit:
        """Create a new visit record."""
        visit = Visit(
            visit_id=uuid.uuid4(),
            person_id=person_id,
            employee_to_meet=employee_to_meet,
            purpose=purpose,
        )
        self.db.add(visit)
        await self.db.flush()
        logger.info("Created visit", visit_id=str(visit.visit_id), person_id=str(person_id))
        return visit

    async def end_visit(self, visit_id: uuid.UUID) -> None:
        """Mark a visit as departed."""
        await self.db.execute(
            update(Visit)
            .where(Visit.visit_id == visit_id)
            .values(
                departure_time=datetime.utcnow(),
                status="departed"
            )
        )

    async def get_active_visits(self) -> List[Visit]:
        """Get all currently active visits."""
        result = await self.db.execute(
            select(Visit)
            .where(Visit.departure_time.is_(None))
            .order_by(Visit.arrival_time.desc())
        )
        return list(result.scalars().all())

    async def get_today_visits(self) -> List[Visit]:
        """Get all visits from today."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)
        result = await self.db.execute(
            select(Visit)
            .where(Visit.arrival_time >= today_start)
            .order_by(Visit.arrival_time.desc())
        )
        return list(result.scalars().all())

    async def delete_person(self, person_id: uuid.UUID) -> bool:
        """Delete a person and all associated data (GDPR compliance)."""
        person = await self.get_person_by_id(person_id)
        if person:
            await self.db.delete(person)
            logger.info("Deleted person", person_id=str(person_id))
            return True
        return False

    async def revoke_consent(self, person_id: uuid.UUID) -> None:
        """Revoke consent and remove biometric data."""
        await self.db.execute(
            update(Person)
            .where(Person.person_id == person_id)
            .values(
                consent_status="revoked",
                face_embedding=None,
                image_path=None
            )
        )
        logger.info("Revoked consent", person_id=str(person_id))

    async def get_all_persons(self, limit: int = 100, offset: int = 0) -> List[Person]:
        """Get all persons with pagination."""
        result = await self.db.execute(
            select(Person)
            .order_by(Person.last_seen.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_visit_stats(self) -> dict:
        """Get visitor statistics."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)

        total_today = await self.db.execute(
            select(func.count(Visit.visit_id))
            .where(Visit.arrival_time >= today_start)
        )
        active = await self.db.execute(
            select(func.count(Visit.visit_id))
            .where(Visit.departure_time.is_(None))
        )
        total_persons = await self.db.execute(
            select(func.count(Person.person_id))
        )

        return {
            "visits_today": total_today.scalar_one(),
            "active_visitors": active.scalar_one(),
            "total_registered": total_persons.scalar_one()
        }
