"""Domain exceptions.

Nothing here imports FastAPI. The repository raises these; the application
translates them into HTTP at its edge. That separation is what makes
`repository.py` testable without starting an app, and it is why a `SELECT`
returning nothing is a `JobNotFound` here rather than an `HTTPException(404)`.
"""


class JobsAPIError(Exception):
    """Base for every error this service raises deliberately."""


class JobNotFound(JobsAPIError):
    """A job id was well-formed but matched no row."""

    def __init__(self, job_id: int) -> None:
        self.job_id = job_id
        super().__init__(f"No job with id {job_id}.")


class DatabaseUnavailable(JobsAPIError):
    """The database is locked by a writer. Transient — retrying is reasonable.

    Raised for `SQLITE_BUSY`, i.e. the busy timeout expired while the scraper
    held its commit lock. The caller should back off and try again.
    """


class DatabaseWedged(JobsAPIError):
    """The database needs human intervention. Retrying will not help.

    Raised for `SQLITE_READONLY_ROLLBACK`: a writer died mid-transaction and
    left a hot journal behind. Recovering it means rolling the journal back,
    which is a *write* — something a read-only connection cannot do, no matter
    how many times it is asked. Distinguishing this from `DatabaseUnavailable`
    is the whole reason both exist.
    """


class SchemaContractError(JobsAPIError):
    """The database is missing a column this service reads.

    The source schema carries no version (`user_version` is 0), so drift cannot
    be detected by comparing a number. Checking the columns directly at startup
    is the only defence available, and it turns a silent wrong answer into a
    loud refusal to start.
    """


class WatchlistNotFound(JobsAPIError):
    """A watchlist id was well-formed but matched no row."""

    def __init__(self, watchlist_id: int) -> None:
        self.watchlist_id = watchlist_id
        super().__init__(f"No watchlist with id {watchlist_id}.")


class WatchlistItemNotFound(JobsAPIError):
    """The watchlist exists; this job is not on it."""

    def __init__(self, watchlist_id: int, job_id: int) -> None:
        self.watchlist_id = watchlist_id
        self.job_id = job_id
        super().__init__(f"Job {job_id} is not on watchlist {watchlist_id}.")


class DuplicateResource(JobsAPIError):
    """A uniqueness constraint refused the write.

    Raised for a 409, and deliberately raised *from* the database's
    `IntegrityError` rather than from a prior SELECT. Checking first and then
    inserting is a time-of-check-to-time-of-use race: two concurrent requests
    can both find nothing and both proceed. The UNIQUE constraint is the only
    thing that can actually decide, so the code lets it decide and translates
    the result.
    """


class ApiKeyRequired(JobsAPIError):
    """A write endpoint was called without a valid key while one is configured."""
