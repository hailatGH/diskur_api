# from .serializers import SidebarSerializer
from rest_framework_jwt.utils import jwt_payload_handler
from moogts.models import Moogt
from invitations.models import Invitation
from meda.enums import InvitationStatus
from users.models import MoogtMedaUser
from firebase_admin import auth

def custom_jwt_payload_handler(user):
    moogts_count = user.proposition_moogts.count()

    subscribers_count = user.followers.count()
    subscribeds_count = user.followings.count()

    open_invitations_count = user.sent_invitations.filter(status=InvitationStatus.PENDING.name).count()

    data = { **jwt_payload_handler(user), 
                "moogts_count": moogts_count, 
                "subscribers_count": subscribers_count, 
                "open_invitations_count": open_invitations_count,
                "first_name": user.first_name,
                "last_name": user.last_name }

    return data

def verify_firebase_user(id_token):
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except:
        return None
    