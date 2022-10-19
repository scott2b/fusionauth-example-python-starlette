import os
import urllib
import pkce
from fusionauth.fusionauth_client import FusionAuthClient
from starlette.applications import Starlette
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.routing import Route, Mount
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

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


templates = Jinja2Templates(directory='templates')


def fusionauth_login_url(code_challenge, scope="offline_access"):
    """offline_access scope is specified in order to recieve a refresh token."""
    callback = urllib.parse.quote_plus("http://localhost:8000%s" % app.url_path_for("oauth_callback"))
    return f"http://{FUSIONAUTH_HOST_IP}:{FUSIONAUTH_HOST_PORT}/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&code_challenge={code_challenge}&code_challenge_method=S256&scope={scope}&redirect_uri={callback}"


def render(template, context=None):
    if context is None:
        context = {}
    return templates.TemplateResponse(template, context)


async def homepage(request):
    return render('index.html', {'request': request})


async def login(request):
    code_verifier, code_challenge = pkce.generate_pkce_pair()
    # save the verifier in session to send it later to the token endpoint
    request.session['code_verifier'] = code_verifier
    return RedirectResponse(url=fusionauth_login_url(code_challenge))


def oauth_callback(request):
    request.user = UnauthenticatedUser()
    if "access_token" in request.session:
        del request.session["access_token"]
    if "refresh_token" in request.session:
        del request.session["refresh_token"]
    if not request.query_params.get("code"):
        return render(
            "error.html", dict(
            msg="Failed to get auth token.",
            reason=request.args["error_reason"],
            description=request.args["error_description"])
        )
    uri = app.url_path_for("oauth_callback")
    tok_resp = client.exchange_o_auth_code_for_access_token_using_pkce(
        request.args.get("code"),
        uri,
        request.session['code_verifier'],
        CLIENT_ID,
        CLIENT_SECRET,
    )
    if not tok_resp.was_successful():
        return render(
            "error.html", dict(
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
            msg="Failed to get user info.",
            reason=tok_resp.error_response["error_reason"],
            description=tok_resp.error_response["error_description"])
        )
    registrations = user_resp.success_response["user"]["registrations"]
    if not user_is_registered(registrations):
        return render(
            "error.html", dict(
            msg="User not registered for this application.",
            reason="Application id not found in user object.",
            description="Did you create a registration for this user and this application?")
        )
    request.user = User(**user_resp.success_response["user"])
    request.session["access_token"] = access_token
    request.session["refresh_token"] = refresh_token
    return redirect("/")



routes = [
    Route('/', endpoint=homepage),
    Route('/login', endpoint=login),
    Route('/oauth-callback', endpoint=oauth_callback),
    Mount('/static', StaticFiles(directory='static'), name='static')
]

app = Starlette(debug=True, routes=routes)
app.add_middleware(AuthenticationMiddleware, backend=backends.SessionAuthBackend())
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie=SESSION_COOKIE,
    max_age=SESSION_EXPIRE_SECONDS,
    same_site=SESSION_SAME_SITE,
    https_only=False, # False recommended for development only
)
