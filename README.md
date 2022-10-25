# fusionauth-example-python-starlette
Example FusionAuth client application demonstrating user registration and authentication

## Update

I have introduced a `USE_TOKENS=False` setting which implements a revised workflow that
mitigates a lot of the previous complexity in session managment. This affects both
OAuth and form-based authentication flows because the previous implementation used
access and refresh tokens on the backend to handle retrieving user info within the
request cycle.

This new approach tracks the user ID in the session in lieu of the OAuth tokens, then
fetches the user info in the backend directly via the API rather than by an access
request. As such, the following changes are enabled when use tokens is set to False:

- No need to enable refresh token generation or scope in the application configuration
- The access token is only used for initial authentication, thus having a very short lifecycle and JWTs can be configured with a short timeout accordingly.
- JWTs are never exposed to the session. Only the user ID is exposed to the session store, therefore Starlette's internal session implementation should suffice.
- Nothing needs to be revoked at logout. For form-based (backend API based) authentication, nothing beyond the standard application logout process is required. For OAuth based authentication, you will want to forward the user to FusionAuth's logout (although I recommend disabling "Keep me signed in" -- see below).


### Disable "Keep me signed in"

As far as I can tell, there is no benefit or utility really to the "Keep me signed in"
checkbox in the FusionAuth login form. I suppose the benefit might be for admins who
actually have a need to access FusionAuth itself, but I do not see a way to pass that
information back to the application -- thus it seems like this option would only serve
to confuse standard users. I recommend disabling the option for this workflow. To do this:

Create a custom theme if you have not already, then delete the following segment from
the theme's "OAuth authorize" template:

```
         [@helpers.input id="rememberDevice" type="checkbox" name="rememberDevice" label=theme.message('remember-device') value="true" uncheckedValue="false"]
            <i class="fa fa-info-circle" data-tooltip="${theme.message('{tooltip}remember-device')}"></i>[#t/]
          [/@helpers.input]
```

Note that if you do not have a FusionAuth license which enables application-specific themes,
you will need to apply the custom theme to the tenant rather than directly on the application.


### Alternative workflows

I have not investigated workflows relevant to, e.g., single-page apps or mobile apps.
These types of applications often hold onto access tokens on the client side and issue
authentication requests directly from the client. I do not recommend these types of
workflows with FusionAuth for the simple reason that irrevocable JWTs are issued as the
access tokens. For more information about why this is a problem, see [This blog post](http://cryto.net/~joepie91/blog/2016/06/13/stop-using-jwt-for-sessions/)
and the [flow chart here](http://cryto.net/%7Ejoepie91/blog/2016/06/19/stop-using-jwt-for-sessions-part-2-why-your-solution-doesnt-work/).
If you need this functionality, I recommend keeping an eye on [FusionAuth RFC 7009](https://github.com/FusionAuth/fusionauth-issues/issues/201)
and upvoting it for implementation of access token revocability.


## Installation

```
pip install -r requirements.txt
```

## Execution

```
uvicorn main:app --reload
```

## About

This is a super-basic attempt at a Starlette application which uses [FusionAuth](https://fusionauth.io/)
for authentication.

The starting point for this was the [Flask example](https://github.com/FusionAuth/fusionauth-example-python-flask)
or more specifically really, [this branch of my fork of the Flask example](https://github.com/scott2b/fusionauth-example-python-flask/tree/session_with_refresh).
Through these explorations in integrating with Flask and Starlette, I made the
decision that FusionAuth's OAuth based workflow is not the right thing for me, and as
such, I will not be submitting the Flask example branch for PR, and do not very
highly recommend enabling `USE_OAUTH` in the current code. The amount of code you would
need to copy into a project for the backend/API based auth workflow is significantly
less than the overall code here, and I've tried to annotate things accordingly.

### OAuth caveats

If you do decide to use the OAuth workflow, please pay attention to the numerous
caveats I have noted in both repositories. The current approach attempts to mitigate
the issues I ran into, but if you believe you can fully solve the problems of JWT
access tokens, then I recommend spending some time with [this flow chart](http://cryto.net/%7Ejoepie91/blog/2016/06/19/stop-using-jwt-for-sessions-part-2-why-your-solution-doesnt-work/).

I have further noted my concerns in my reply to [RFC 7009](https://github.com/FusionAuth/fusionauth-issues/issues/201)
which I believe is worth keeping an eye on. In short, the things I would need to see
implemented in order to consider using OAuth based authentication in FusionAuth would
minimally include:

- Stop using JWTs for access tokens
- Ability to revoke all tokens, (access and refresh) for a given user -- preferrably on a per-application basis.
- Demonstrable administrative authentication revocation workflow which does not respawn deleted users or user registrations due to lingering tokens or sessions.
- Fixing of whatever it is that causes Firefox to initiate downloading of a file during logout.

Note: I have not even begun to explore SSO, which I suspect is prone to some of the
same issues as FusionAuth's builtin OAuth.


### Backend/API based authentication workflow

As-is (with `USE_OAUTH` set to `False`) the current project seems more secure to me. I
am not a security expert, but so far I don't see a reason not to use this approach if
the workflow suffices for your needs. It's a bit of additional work: you have to build 
your own login form, for example, but I think it is worth it. I do recommend:

- Use server-side session management (a basic filesystem based approach is shown. The same library supports Redis)
- Only serve your site over https 
- Use some kind of csrf checking (not demonstrated here)

Note that it is possible to use FusionAuth's builtin registration instead of doing an
API call, for instance by ensuring self-registered users do not have any default
accesses to the FusionAuth platform ... but I still think it is worth simply building
your own registration forms and making the register API call on the backend.


## General Use case

FusionAuth is a full featured and extremely flexible platform for handling not only
user authentication and application registration, but also things like groups, ACL, etc.
I have not even begun to explore the range or depth of the possibilities for
authentication or authorization. The use case explored here is a simple one: self-registered
user authentication for which sessions and authorization are handled by a "traditional"
web application. There is a lot of capability in FusionAuth I simply have not yet
explored, but also probably won't until I see usable OAuth and SSO workflows.

## Additional notes

### `logout` API calls

As noted in the comments: the `logout` call to the API does not really seem to do
anything even when the refresh token is explicitly passed for revocation. Instead,
revoke refresh tokens explicitly via a call to `revoke_refresh_token` as shown.

### Apache license

I tend to reach for MIT in most of my projects, but for no particular reason. I have
attached an Apache license to this because there are bound to be some lingering
copy-pastes from the [Flask example](https://github.com/FusionAuth/fusionauth-example-python-flask)
which started me on this journey and which uses the Apache license.
