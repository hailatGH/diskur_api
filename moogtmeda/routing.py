from .channels_middleware import TokenAuthMiddleware
from channels.routing import ProtocolTypeRouter, URLRouter
import chat.routing
import moogts.routing

# The channel routing defines what connections get handled by what consumers,
# selecting on either the connection type (ProtocolTypeRouter) or properties
# of the connection's scope (like URLRouter, which looks at scope["path"])
# For more, see http://channels.readthedocs.io/en/latest/topics/routing.html
application = ProtocolTypeRouter({
    'websocket': TokenAuthMiddleware(
        URLRouter(
            # URLRouter just takes standard Django path() or url() entries.
            chat.routing.websocket_urlpatterns + moogts.routing.websocket_urlpatterns
        )
    ),
})
