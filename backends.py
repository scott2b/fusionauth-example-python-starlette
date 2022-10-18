from starlette.authentication import AuthenticationBackend, AuthCredentials


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
        user = UnauthenticatedUser()
        creds = []
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
        return AuthCredentials(creds), user
