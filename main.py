import os
import urllib
import pkce
from fusionauth.fusionauth_client import FusionAuthClient
from starlette.applications import Starlette
from starlette.middleware.authentication import AuthenticationMiddleware
# from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.routing import Route, Mount
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles
from starsessions import load_session, SessionMiddleware
from starsessions.session import regenerate_session_id


import backends


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
    """offline_access scope is specified in order to recieve a refresh token."""
    callback = urllib.parse.quote_plus("http://localhost:8000%s" % app.url_path_for("oauth_callback"))
    return f"http://{FUSIONAUTH_HOST_IP}:{FUSIONAUTH_HOST_PORT}/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&code_challenge={code_challenge}&code_challenge_method=S256&scope={scope}&redirect_uri={callback}"


def fusionauth_logout_url():
    """
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
    return render('index.html', {'request': request})


async def register(request):
    """To use registration, enable self-service registration in the Registration tab of
    the application configuration in FusionAuth. You may also want to enable specific
    registration properties such as First Name and Last Name to be passed into the
    User constructor.
    """
    code_verifier, code_challenge = pkce.generate_pkce_pair()

    # See [starsession documentation](https://github.com/alex-oleshkevich/starsessions#session-autoload) for autoloading
    await load_session(request)
    request.session["code_verifier"] = code_verifier
    return RedirectResponse(fusionauth_register_url(code_challenge))


async def login(request):
    code_verifier, code_challenge = pkce.generate_pkce_pair()
    # save the verifier in session to send it later to the token endpoint
    await load_session(request)
    request.session['code_verifier'] = code_verifier
    return RedirectResponse(url=fusionauth_login_url(code_challenge))


async def login_form(request):
    # https://fusionauth.io/docs/v1/tech/apis/login#authenticate-a-user
    data = await request.form()
    print(data["email"], data["password"])
    resp = client.login({
      "loginId": data["email"],
      "password": data["password"],
      "applicationId": CLIENT_ID,
      "noJWT" : False,
      #"ipAddress": "192.168.1.42"
    })
    print(resp)
    print(dir(resp))
    print('error_response', resp.error_response)
    print('exception', resp.exception)
    print('response', resp.response)
    print('status', resp.status)
    print('success_response', resp.success_response)
    print('was_successful', resp.was_successful())
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
    request.session["access_token"] = data["token"]
    request.session["refresh_token"] = data["refreshToken"]
    return RedirectResponse(url="/", status_code=303)

# To receive a refresh token, be sure to set "Generate refresh tokens" in the security tab of the application


async def logout(request):
    # form-based login:
    await load_session(request)
    # NOTE: it is not really clear what this logout call does, if anything. It does not
    # invalidate the access token (by design), and it does not appear to be invalidating
    # the refresh token either, despite the explicit passing of the token. Thus we will
    # make a subsequent call to revoke the token directly below.
    resp = client.logout(False, refresh_token=request.session["refresh_token"])
    revoke_resp = client.revoke_refresh_tokens_by_application_id(CLIENT_ID)
    request.session.clear()
    # Note the access token, if leaked, will still be valid at this point until it
    # times out. By design, FusionAuth does not provide a mechanism for revoking access tokens.
    return RedirectResponse("/")

    # OAuth:
    revoke_resp = client.revoke_refresh_tokens_by_application_id(CLIENT_ID)
    # TODO: should we check for success?
    # IMPORTANT: For the access token especially, if we do not delete it from
    # the session, the user will still be logged in for the duration of the token's
    # lifetime, which is specified by the application's "JWT duration" setting in
    # FusionAuth. FusionAuth does not provide a way to invalidate the access token.
    # See [RFC 7009](https://github.com/FusionAuth/fusionauth-issues/issues/201)
    await load_session(request)
    #if "access_token" in request.session:
    #    del request.session["access_token"]
    #if "refresh_token" in request.session:
    #    del request.session["refresh_token"]
    request.session.clear()
    return RedirectResponse(url=fusionauth_logout_url())


async def oauth_callback(request):
    #request.user = UnauthenticatedUser()
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
    #request.user = User(**user_resp.success_response["user"])
    request.session["access_token"] = access_token
    request.session["refresh_token"] = refresh_token
    return RedirectResponse(url="/")



routes = [
    Route('/', endpoint=homepage),
    Route('/register', endpoint=register),
    Route('/login', endpoint=login),
    Route('/login-form', endpoint=login_form, methods=["GET", "POST"]),
    Route('/logout', endpoint=logout),
    Route('/oauth-callback', endpoint=oauth_callback),
    Mount('/static', StaticFiles(directory='static'), name='static')
]


app = Starlette(debug=True, routes=routes)
app.add_middleware(AuthenticationMiddleware, backend=backends.SessionAuthBackend())
#app.add_middleware(
#    SessionMiddleware,
#    secret_key=SECRET_KEY,
#    session_cookie=SESSION_COOKIE,
#    max_age=SESSION_EXPIRE_SECONDS,
#    same_site=SESSION_SAME_SITE,
#    https_only=False, # False recommended for development only
#)

from store import FilesystemStore

session_store = FilesystemStore()

app.add_middleware(
    SessionMiddleware,
    store=session_store,
    cookie_https_only=False, # False for development only
    # lifetime=3600 * 24 * 14, # default is the browser session rather than a time period
                               # There is also a [rolling sessions](https://github.com/alex-oleshkevich/starsessions#rolling-sessions) option
)

