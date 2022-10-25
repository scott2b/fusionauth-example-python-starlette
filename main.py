import os
import urllib
import pkce
from fusionauth.fusionauth_client import FusionAuthClient
from starlette.applications import Starlette
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.routing import Route, Mount
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles
from starsessions import load_session, SessionMiddleware
from starsessions.session import regenerate_session_id
from store import FilesystemStore
import backends


"""
Use FusionAuth's OAuth authentication with caution. There seem to be several known
issues. Some of these are spelled out more explicitly in this branch of a fork of the
Flask example: https://github.com/scott2b/fusionauth-example-python-flask/tree/session_with_refresh

In particular, Fusion's use of JWTs as OAuth access tokens, and the inability to revoke
said tokens creates some tricky security situations. Keep an eye on [this RFC](https://github.com/FusionAuth/fusionauth-issues/issues/201)
for access token revocation as a feature.

Additionally, FusionAuth sets cookies during the OAuth login process and does not always
seem to handle these correctly. I have seen inconsistencies in when/whether cookies are
actually set, and cookies do not seem to be properly revoked during logout, resulting in
such behaviors as re-spawned sessions and re-generated deleted users or user roles. I
suspect there are similar issues when using an SSO workflow, although I have not explored
this possibility.

In short, I do not recommend using FusionAuth's OAuth without considerable diligence done
on the overall authentication and authorization workflow of your application. Beware of
the potential for FusionAuth to leak access permissions if the workflow is not carefully
locked down. The fixes presented here are mitigating workarounds at best. My current
solution is to only use FusionAuth's login API until I better understand how FusionAuth
is meant to be used securely.
"""
USE_OAUTH = False # whether ot use oauth for initial auth. Ongoing session management via tokens is controlled by USE_TOKENS
USE_TOKENS = backends.USE_TOKENS


SECRET_KEY = os.environ.get("SECRET_KEY", "supersecret__changeme")
SESSION_COOKIE = os.environ.get("SESSION_COOKIE", "fa.example.starlette")
SESSION_EXPIRE_SECONDS = int(os.environ.get("SESSION_EXPIRE_SECONDS", 60*60*24*10))
SESSION_SAME_SITE = os.environ.get("SESSION_SAME_SITE", "lax") # lax, strict, or none

API_KEY = os.environ["FUSIONAUTH_API_KEY"]
CLIENT_ID = os.environ["FUSIONAUTH_CLIENT_ID"]
CLIENT_SECRET = os.environ["FUSIONAUTH_CLIENT_SECRET"]
FUSIONAUTH_HOST_IP = os.environ.get("FUSIONAUTH_HOST_IP", "localhost")
FUSIONAUTH_HOST_PORT = os.environ.get("FUSIONAUTH_HOST_PORT", "9011")


client = FusionAuthClient(API_KEY, f"http://{FUSIONAUTH_HOST_IP}:{FUSIONAUTH_HOST_PORT}")
templates = Jinja2Templates(directory='templates')

"""
If using OAuth:

Any callback / redirect URLs must be specified in the "Authorized Redirect URLs" for the
application OAuth config in FusionAuth.

Be aware of trailing slash issues when configuring these URLs. E.g. Flask's url_for
will include a trailing slash here on `url_for("index")`
"""

def fusionauth_register_url(code_challenge, scope="offline_access"):
    """offline_access scope is specified in order to recieve a refresh token."""
    callback = urllib.parse.quote_plus("http://localhost:8000%s" % app.url_path_for("oauth_callback"))
    return f"http://{FUSIONAUTH_HOST_IP}:{FUSIONAUTH_HOST_PORT}/oauth2/register?client_id={CLIENT_ID}&response_type=code&code_challenge={code_challenge}&code_challenge_method=S256&scope={scope}&redirect_uri={callback}"


def fusionauth_login_url(code_challenge, scope="offline_access"):
    """
    Only needed for USE_OAUTH=True.

    offline_access scope is specified in order to recieve a refresh token.
    """
    callback = urllib.parse.quote_plus("http://localhost:8000%s" % app.url_path_for("oauth_callback"))
    return f"http://{FUSIONAUTH_HOST_IP}:{FUSIONAUTH_HOST_PORT}/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&code_challenge={code_challenge}&code_challenge_method=S256&scope={scope}&redirect_uri={callback}"


def fusionauth_logout_url():
    """
    Only needed for USE_OAUTH=True.

    Alternatively to specifying the `post_logout_redirect_uri`, set the Logout URL in
    the application configuration OAuth tab.
    """
    redir = urllib.parse.quote_plus("http://localhost:8000%s" % app.url_path_for("homepage"))
    return f"http://{FUSIONAUTH_HOST_IP}:{FUSIONAUTH_HOST_PORT}/oauth2/logout?client_id={CLIENT_ID}&post_logout_redirect_uri={redir}"


def render(template, context=None):
    if context is None:
        context = {}
    return templates.TemplateResponse(template, context)


async def homepage(request):
    if USE_OAUTH:
        return render('index-oauth.html', {'request': request})
    else:
        return render('index-loginform.html', {'request': request})


async def register(request):
    """For OAuth: To use registration, enable self-service registration in the Registration tab of
    the application configuration in FusionAuth. You may also want to enable specific
    registration properties such as First Name and Last Name to be passed into the
    User constructor.

    For API-based registration, note that this process creates both a user and the
    registration. You may require a different workflow if, for example, the user
    already exists in your FusionAuth system. See the FusionAuth API docs for
    registrations: https://fusionauth.io/docs/v1/tech/apis/registrations

    Note: if you expose self-registration, either with FusionAuth's form or with your
    own, administratively deactivated users should be marked "deactivated" rather than
    deleted or they will simple be able to re-register. Currently, the check for this is
    handled in the backends.user_is_registered function.
    """
    # See [starsession documentation](https://github.com/alex-oleshkevich/starsessions#session-autoload) for autoloading
    await load_session(request)
    if USE_OAUTH:
        # Note that it is possible to use this registration process when not otherwise
        # using OAuth for authentication. The workflow is prone to some of the same
        # issues as otherwise noted for OAuth, although in some cases the risk may be
        # minimal. For example, a lingering FusionAuth session for a newly registered
        # user might not really be an issue if that user does not have any actual
        # permissions into FusionAuth itself. For my part, I've chosen to simply build
        # my own registration forms and register via the API as in the else section
        # below.
        code_verifier, code_challenge = pkce.generate_pkce_pair()
        request.session["code_verifier"] = code_verifier
        return RedirectResponse(fusionauth_register_url(code_challenge))
    else:
        errors = None
        if request.method == "POST":
            form = await request.form()
            data = {
                "registration": {
                    "applicationId": CLIENT_ID
                },
                "user": {
                    "email": form["email"],
                    "firstName": form["firstName"],
                    "lastName": form["lastName"],
                    "password": form["password"]
                }
            }
            # https://github.com/FusionAuth/fusionauth-python-client/blob/master/src/main/python/fusionauth/fusionauth_client.py#L1975
            register_resp = client.register(data)
            if register_resp.was_successful():
                return RedirectResponse(url=request.url_for("homepage"), status_code=303)
            # TODO: better error handling
            errors = register_resp.error_response
        return render("register.html", { 'request': request, 'errors': errors })



async def login(request):
    code_verifier, code_challenge = pkce.generate_pkce_pair()
    # save the verifier in session to send it later to the token endpoint
    await load_session(request)
    request.session['code_verifier'] = code_verifier
    return RedirectResponse(url=fusionauth_login_url(code_challenge))


async def login_form(request):
    # https://fusionauth.io/docs/v1/tech/apis/login#authenticate-a-user
    data = await request.form()
    resp = client.login({
      "loginId": data["email"],
      "password": data["password"],
      "applicationId": CLIENT_ID,
      "noJWT" : False,
      #"ipAddress": "192.168.1.42"
    })
    if not resp.status == 200:
        raise Exception # TODO: handle cases
    data = resp.success_response
    regenerate_session_id(request)
    await load_session(request)
    request.session.clear()
    registrations = data["user"]["registrations"]
    if not backends.user_is_registered(registrations):
        return render(
            "error.html", dict(
            request=request,
            msg="User not registered for this application.",
            reason="Application id not found in user object.",
            description="Did you create a registration for this user and this application?")
        )
    #request.user = User(**user_resp.success_response["user"])

    if USE_TOKENS:
        request.session["access_token"] = data["token"]
        request.session["refresh_token"] = data["refreshToken"]
    else:
        request.session["user_id"] = data["user"]["id"]
    return RedirectResponse(url="/", status_code=303)



async def logout(request):
    if USE_OAUTH:
        #revoke_resp = client.revoke_refresh_tokens_by_application_id(CLIENT_ID)
        # TODO: should we check for success?
        # IMPORTANT: For the access token especially, if we do not delete it from
        # the session, the user will still be logged in for the duration of the token's
        # lifetime, which is specified by the application's "JWT duration" setting in
        # FusionAuth. FusionAuth does not provide a way to invalidate the access token.
        # See [RFC 7009](https://github.com/FusionAuth/fusionauth-issues/issues/201)

        # Note that FusionAuth's logout page does a weird thing in Firefox where it
        # tries to download an empty file called single-logout.
        # See: https://fusionauth.io/community/forum/topic/2209/logout-triggers-a-file-download-in-firefox?_=1666224554722
        await load_session(request)
        if USE_TOKENS:
            revoke_resp = client.revoke_refresh_token(request.session["refresh_token"])
        request.session.clear() # delete the tokens if used, otherwise deletes the user_id
        return RedirectResponse(url=fusionauth_logout_url())
    else:
        await load_session(request)
        # NOTE: While the client exposes a logout method, it is not really clear what
        # the logout call does, if anything. It does *NOT* invalidate the access token
        # nor the refresh token, even if the token is explicitly passed to the logout
        # method. Wrt to the access token, this is by design (see other notes on
        # access token revocation. Wrt the refresh token, this is almost certainly a bug.
        #
        # Thus, we call revoke_refresh_token directly.
        if USE_TOKENS:
            revoke_resp = client.revoke_refresh_token(request.session["refresh_token"])
        request.session.clear() # delete the tokens or the user_id
        # Note the access token, if leaked, will still be valid at this point until it
        # times out. By design, FusionAuth does not provide a mechanism for revoking access tokens.
        return RedirectResponse("/")


async def oauth_callback(request):
    """This callback is only needed for USE_OAUTH=True. See caveats in notes for that
    setting above.
    """
    regenerate_session_id(request)
    await load_session(request)
    if "access_token" in request.session:
        del request.session["access_token"]
    if "refresh_token" in request.session:
        del request.session["refresh_token"]
    if not request.query_params.get("code"):
        return render(
            "error.html", dict(
            request=request,
            msg="Failed to get auth token.",
            reason=request.query_params["error_reason"],
            description=request.query_params["error_description"])
        )
    uri = "http://localhost:8000%s" % app.url_path_for("oauth_callback")
    tok_resp = client.exchange_o_auth_code_for_access_token_using_pkce(
        request.query_params.get("code"),
        uri,
        request.session['code_verifier'],
        CLIENT_ID,
        CLIENT_SECRET,
    )
    if not tok_resp.was_successful():
        return render(
            "error.html", dict(
            request=request,
            msg="Failed to get auth token.",
            reason=tok_resp.error_response["error_reason"],
            description=tok_resp.error_response["error_description"])
        )
    access_token = tok_resp.success_response["access_token"]
    if USE_TOKENS:
        refresh_token = tok_resp.success_response.get("refresh_token")
        assert refresh_token is not None, 'To receive a refresh token, be sure to enable ' \
            '"Generate Refresh Tokens" for the app, and specify `scope=offline_access` in '\
            'the request to the authorize endpoint.'
    user_resp = client.retrieve_user_using_jwt(access_token)
    if not user_resp.was_successful():
        return render(
            "error.html", dict(
            request=request,
            msg="Failed to get user info.",
            reason=tok_resp.error_response["error_reason"],
            description=tok_resp.error_response["error_description"])
        )
    registrations = user_resp.success_response["user"]["registrations"]
    if not backends.user_is_registered(registrations):
        return render(
            "error.html", dict(
            request=request,
            msg="User not registered for this application.",
            reason="Application id not found in user object.",
            description="Did you create a registration for this user and this application?")
        )
    if USE_TOKENS:
        request.session["access_token"] = access_token
        request.session["refresh_token"] = refresh_token
    else:
        request.session["user_id"] = user_resp.success_response["user"]["id"] 
    return RedirectResponse(url="/")


routes = [
    Route('/', endpoint=homepage),
    Route('/register', endpoint=register, methods=["GET", "POST"]),
    Route('/login', endpoint=login),
    Route('/login-form', endpoint=login_form, methods=["GET", "POST"]),
    Route('/logout', endpoint=logout),
    Route('/oauth-callback', endpoint=oauth_callback),
    Mount('/static', StaticFiles(directory='static'), name='static')
]


app = Starlette(debug=True, routes=routes)
app.add_middleware(AuthenticationMiddleware, backend=backends.SessionAuthBackend())


session_store = FilesystemStore() # Should probably not use the fs store in production

app.add_middleware(
    SessionMiddleware,
    store=session_store,
    cookie_https_only=False, # False for development only
    lifetime=3600 * 24 * 14, # Default is the browser session rather than a time period,
                             # although this only works when closing out the browser
                             # entirely, not just closing tabs.
                             # There is also a [rolling sessions](https://github.com/alex-oleshkevich/starsessions#rolling-sessions) option
)

