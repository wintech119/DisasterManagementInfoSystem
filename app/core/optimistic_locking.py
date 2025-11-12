"""
Optimistic Locking Implementation for DRIMS
Uses version_nbr column to prevent concurrent modification conflicts
"""
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import instance_state
from app.core.exceptions import OptimisticLockError
import logging

logger = logging.getLogger(__name__)


def setup_optimistic_locking(db):
    """
    Register optimistic locking event listeners on the SQLAlchemy session.
    
    This ensures that all UPDATE operations on tables with version_nbr
    include the version number in the WHERE clause and increment it.
    """
    
    @event.listens_for(Session, "before_flush")
    def enforce_optimistic_lock(session, flush_context, instances):
        """
        Before flush event: For all dirty objects with version_nbr,
        execute a manual UPDATE with version_nbr in WHERE clause.
        """
        for obj in list(session.dirty):
            if not hasattr(obj, 'version_nbr'):
                continue
            
            if not session.is_modified(obj):
                continue
            
            state = instance_state(obj)
            mapper = state.mapper
            table = mapper.local_table
            
            if 'version_nbr' not in table.c:
                continue
            
            history = state.attrs.version_nbr.history
            if history.has_changes():
                continue
            
            current_version = obj.version_nbr
            if current_version is None:
                logger.warning(
                    f"Object {obj.__class__.__name__} has None version_nbr, skipping optimistic lock"
                )
                continue
            
            pk_columns = [col for col in mapper.primary_key]
            pk_dict = {col.name: getattr(obj, col.name) for col in pk_columns}
            
            update_values = {}
            for attr in state.attrs:
                if attr.key == 'version_nbr':
                    continue
                if attr.history.has_changes():
                    update_values[attr.key] = getattr(obj, attr.key)
            
            if not update_values:
                continue
            
            update_values['version_nbr'] = current_version + 1
            
            stmt = table.update()
            for col_name, col_value in pk_dict.items():
                stmt = stmt.where(table.c[col_name] == col_value)
            stmt = stmt.where(table.c.version_nbr == current_version)
            stmt = stmt.values(**update_values)
            
            result = session.execute(stmt)
            
            if result.rowcount == 0:
                session.rollback()
                raise OptimisticLockError(
                    obj.__class__.__name__,
                    pk_dict,
                    f"Stale version {current_version} - record was modified by another transaction"
                )
            
            obj.version_nbr = current_version + 1
            
            session.expire(obj)
    
    logger.info("Optimistic locking enabled for all tables with version_nbr")
