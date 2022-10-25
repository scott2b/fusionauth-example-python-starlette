import os
from starlette.authentication import AuthenticationBackend, AuthCredentials
from fusionauth.fusionauth_client import FusionAuthClient
from starsessions import load_session
from starsessions.session import regenerate_session_id
import pkce


API_KEY = os.environ["FUSIONAUTH_API_KEY"]
CLIENT_ID = os.environ["FUSIONAUTH_CLIENT_ID"]
CLIENT_SECRET = os.environ["FUSIONAUTH_CLIENT_SECRET"]
FUSIONAUTH_HOST_IP = os.environ.get("FUSIONAUTH_HOST_IP", "localhost")
FUSIONAUTH_HOST_PORT = os.environ.get("FUSIONAUTH_HOST_PORT", "9011")

USE_TOKENS = False # False to fetch the user directly from the api instead of using the access and refresh tokens

client = FusionAuthClient(API_KEY, f"http://{FUSIONAUTH_HOST_IP}:{FUSIONAUTH_HOST_PORT}")


def user_is_registered(registrations, app_id=CLIENT_ID):
    return all([
        registrations is not None,
        len(registrations) > 0,
        any(r["applicationId"] == app_id and not "deactivated" in r["roles"] for r in registrations)])


### User object

class UnauthenticatedUser:

    @property
    def is_authenticated(self):
        return False


class User:

    def __init__(self, *, active, id, email, insertInstant,
            lastUpdateInstant, lastLoginInstant, passwordLastUpdateInstant,
            passwordChangeRequired, firstName=None, lastName=None, **kwargs):
        """Enable `First name` and `Last name` in the application registration configs if
        you want FusionAuth to provide them to be passed in here.
        """
        # TODO: extract group memberships from `memberships` kwarg
        # TODO: username is application specific and needs to be extracted from registrations
        self.active = active
        self.user_id=id
        self.email=email
        self.first_name = firstName
        self.last_name = lastName
        self.created_at=insertInstant
        self.updated_at=lastUpdateInstant
        self.last_login=lastLoginInstant
        self.pwd_updated_at=passwordLastUpdateInstant
        self.pwd_change_required=passwordChangeRequired

    @property
    def is_authenticated(self):
        return True



class SessionAuthBackend(AuthenticationBackend):

    async def authenticate(self, request):
        await load_session(request)
        user = UnauthenticatedUser()
        creds = []

        if USE_TOKENS:
            access_token = request.session.get("access_token")
            refresh_token = request.session.get("refresh_token")
            if access_token:
                user_resp = client.retrieve_user_using_jwt(access_token)
                if not user_resp.was_successful() and refresh_token:
                    token_resp = client.exchange_refresh_token_for_access_token(
                        refresh_token,
                        client_id=CLIENT_ID,
                        client_secret=CLIENT_SECRET)
                    if token_resp.was_successful():
                        access_token = token_resp.success_response["access_token"]
                        refresh_token = token_resp.success_response["refresh_token"]
                        request.session["access_token"] = access_token
                        request.session["refresh_token"] = refresh_token
                    else:
                        access_token = None
                        refresh_token = None
                if access_token is not None:
                    user_resp = client.retrieve_user_using_jwt(access_token)
                    if user_resp.was_successful():
                        registrations = user_resp.success_response["user"]["registrations"]
                        if user_is_registered(registrations):
                            user = User(**user_resp.success_response["user"])
                        else: # The user registration may have been administratively deleted
                            pass
                creds = ["app_auth"]
                #if user.superuser:
                #    creds.append("admin_auth")
        else:
            # Fetch the user directly from the API.
            user_id = request.session.get("user_id")
            if user_id:
                user_resp = client.retrieve_user(user_id)
                registrations = user_resp.success_response["user"]["registrations"]
                if user_is_registered(registrations):
                    user = User(**user_resp.success_response["user"])
                else: # The user registration may have been administratively deleted
                    pass
                
        return AuthCredentials(creds), user

