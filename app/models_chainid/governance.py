from sqlalchemy import Column, Integer, String, DateTime, Float
from datetime import datetime, timezone

from app.models_chainid.base import Base


class GovernanceProposal(Base):
    __tablename__ = "governance_proposals"

    id = Column(Integer, primary_key=True)

    chain_id = Column(String, index=True)
    proposal_id = Column(Integer, index=True)

    title = Column(String)
    status = Column(String)

    voting_start_time = Column(DateTime)
    voting_end_time = Column(DateTime)

    yes_votes = Column(Float, default=0)
    no_votes = Column(Float, default=0)
    abstain_votes = Column(Float, default=0)
    no_with_veto_votes = Column(Float, default=0)

    validator_voted = Column(Integer, default=0)
    validator_vote_option = Column(String)

    is_latest = Column(Integer, default=1)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
