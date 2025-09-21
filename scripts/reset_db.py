import logging
from sqlalchemy import create_engine, inspect, text
from app.config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def drop_all_tables():
    """Drops all tables in the public schema of the database."""
    if "sqlite" in settings.DATABASE_URL:
        logger.warning("This script is designed for PostgreSQL and might not work with SQLite.")
        # For SQLite, Base.metadata.drop_all(engine) is often sufficient
        # but we are proceeding with a generic approach.

    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as connection:
        try:
            logger.info("Starting transaction to drop all tables...")
            with connection.begin():
                inspector = inspect(engine)
                # This command disables foreign key constraints for the current session
                # to allow dropping tables without order-of-deletion issues.
                logger.info("Disabling foreign key constraints for the session.")
                connection.execute(text("SET session_replication_role = 'replica';"))

                # Get all table names in the 'public' schema
                tables = inspector.get_table_names(schema='public')

                if not tables:
                    logger.info("No tables found in the public schema.")
                    return

                logger.info(f"Found tables to drop: {', '.join(tables)}")

                # Drop all tables
                for table_name in tables:
                    logger.info(f"Dropping table: {table_name}")
                    connection.execute(text(f'DROP TABLE IF EXISTS public."{table_name}" CASCADE;'))

                # Re-enable foreign key constraints
                logger.info("Re-enabling foreign key constraints.")
                connection.execute(text("SET session_replication_role = 'origin';"))

            logger.info("All tables in the public schema have been dropped successfully.")

        except Exception as e:
            logger.error(f"An error occurred: {e}")
            # The transaction will be rolled back automatically by the 'with' statement.
            raise

if __name__ == "__main__":
    drop_all_tables()

