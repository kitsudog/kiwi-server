from sqlalchemy import event, select, exc
# noinspection PyProtectedMember
from sqlalchemy.engine import CreateEnginePlugin, Connectable
from sqlalchemy.events import ConnectionEvents, PoolEvents

from base.style import Log


# noinspection PyUnusedLocal
class PoolHookPlugin(CreateEnginePlugin):
    def __init__(self, url, kwargs):
        super().__init__(url, kwargs)

    def handle_dialect_kwargs(self, dialect_cls, dialect_args):
        """parse and modify dialect kwargs"""

    def handle_pool_kwargs(self, pool_cls, pool_args):
        """parse and modify pool kwargs"""

    def engine_created(self, engine):
        Log(f"CreateEnginePlugin::engine_created[engine={engine}]")

        @event.listens_for(engine, PoolEvents.close.__name__)
        def pool_close(connection: Connectable, branch):
            Log(f"PoolEvents::close[engine={engine}] ok")

        @event.listens_for(engine, ConnectionEvents.engine_connect.__name__)
        def ping_connection(connection: Connectable, branch):
            if branch:
                # "branch" refers to a sub-connection of a connection,
                # we don't want to bother pinging on these.
                return
            # turn off "close with result".  This flag is only used with
            # "connectionless" execution, otherwise will be False in any case
            save_should_close_with_result = connection.should_close_with_result
            connection.should_close_with_result = False

            try:
                # run a SELECT 1.   use a core select() so that
                # the SELECT of a scalar value without a table is
                # appropriately formatted for the backend
                connection.scalar(select([1]))
                Log(f"ConnectionEvents::engine_connect[engine={engine}] ok")
            except exc.DBAPIError as err:
                # catch SQLAlchemy's DBAPIError, which is a wrapper
                # for the DBAPI's exception.  It includes a .connection_invalidated
                # attribute which specifies if this connection is a "disconnect"
                # condition, which is based on inspection of the original exception
                # by the dialect in use.
                if err.connection_invalidated:
                    # run the same SELECT again - the connection will re-validate
                    # itself and establish a new connection.  The disconnect detection
                    # here also causes the whole connection pool to be invalidated
                    # so that all stale connections are discarded.
                    connection.scalar(select([1]))
                else:
                    raise
            finally:
                # restore "close with result"
                connection.should_close_with_result = save_should_close_with_result
