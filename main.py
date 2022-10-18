import os
from starlette.applications import Starlette
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Route, Mount
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles
import backends

SECRET_KEY = os.environ.get("SECRET_KEY", "supersecret__changeme")
SESSION_COOKIE = os.environ.get("SESSION_COOKIE", "fa.example.starlette")
SESSION_EXPIRE_SECONDS = int(os.environ.get("SESSION_EXPIRE_SECONDS", 60*60*24*10))
SESSION_SAME_SITE = os.environ.get("SESSION_SAME_SITE", "lax") # lax, strict, or none


templates = Jinja2Templates(directory='templates')

async def homepage(request):
    return templates.TemplateResponse('index.html', {'request': request})

routes = [
    Route('/', endpoint=homepage),
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
